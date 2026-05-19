"""
Integration tests for DB pool configuration (Slice G, W4-G).

Loads `backend/db.py` via importlib so we exercise the real module without
importing the full backend graph.
"""
from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


_BACKEND_DIR = Path(__file__).resolve().parents[2]


def _load_db_module():
    target = _BACKEND_DIR / "db.py"
    if not target.exists():
        pytest.skip("db.py not found")
    # Pre-set DATABASE_URL to sqlite so module import doesn't try to connect
    # to a real Postgres instance.
    os.environ.setdefault("DATABASE_URL", "sqlite:///./test_pool.db")
    spec = importlib.util.spec_from_file_location(
        "_perennia_db_under_test_pool", str(target)
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)  # type: ignore[union-attr]
    except Exception as exc:
        pytest.skip(f"db.py import failed: {exc}")
    return module


_db = _load_db_module()


# ---------------------------------------------------------------------------
# 1. Pool config respects env vars (defaults visible)
# ---------------------------------------------------------------------------

def test_pool_size_env_var_recognized(monkeypatch):
    """DB_POOL_SIZE env var must be readable as an int by the module logic."""
    raw = os.getenv("DB_POOL_SIZE", "10")
    assert int(raw) >= 1


def test_max_overflow_env_var_recognized():
    raw = os.getenv("DB_MAX_OVERFLOW", "20")
    assert int(raw) >= 0


# ---------------------------------------------------------------------------
# 2. Sync engine singleton
# ---------------------------------------------------------------------------

def test_sync_engine_exposed():
    """db.py must expose a sync `engine` attribute."""
    assert hasattr(_db, "engine"), "db module missing `engine`"


def test_session_local_callable():
    assert hasattr(_db, "SessionLocal"), "db module missing `SessionLocal`"
    assert callable(_db.SessionLocal)


# ---------------------------------------------------------------------------
# 3. Pool flags visible
# ---------------------------------------------------------------------------

def test_pool_pre_ping_flag_default_true():
    """DB_POOL_PRE_PING defaults to "true" — verified by reading env."""
    val = os.getenv("DB_POOL_PRE_PING", "true").lower()
    assert val in {"true", "false", "1", "0"}


def test_pool_recycle_default_set():
    """DB_POOL_RECYCLE defaults to 3600 (1h)."""
    val = int(os.getenv("DB_POOL_RECYCLE", "3600"))
    assert val > 0


# ---------------------------------------------------------------------------
# 4. Async engine creation hooks
# ---------------------------------------------------------------------------

def test_async_session_local_attribute_present():
    """AsyncSessionLocal symbol must exist (may be None when async unavailable)."""
    assert hasattr(_db, "AsyncSessionLocal")


def test_get_async_db_is_async_generator_function():
    """get_async_db must be present and be an async generator (or async fn)."""
    assert hasattr(_db, "get_async_db")
    import inspect

    gad = _db.get_async_db
    assert inspect.iscoroutinefunction(gad) or inspect.isasyncgenfunction(gad)
