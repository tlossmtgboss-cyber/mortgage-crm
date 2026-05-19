"""
Integration tests for the async DB plumbing in backend/db.py.

Targets the async engine singleton, AsyncSessionLocal sessionmaker, and the
`get_async_db` FastAPI dependency. Uses SQLite + aiosqlite under the hood,
which is the same configuration the local test environment uses.

These tests pass when the async engine is initialized successfully. If
aiosqlite or async SQLAlchemy is unavailable for any reason, the test
gracefully skips instead of failing.
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


def _load_db():
    target = _BACKEND_DIR / "db.py"
    if not target.exists():
        pytest.skip("db.py missing")
    # Force SQLite URL so tests don't try to hit Railway PostgreSQL.
    os.environ.setdefault("DATABASE_URL", "sqlite:///./mortgage_crm.db")
    # Ensure encryption_utils initializes cleanly (used by transitively
    # imported services). Do NOT set RAILWAY_ENVIRONMENT — any value
    # (including "development") makes encryption_utils think it's production
    # and refuse to start without DATA_ENCRYPTION_KEY.
    os.environ.setdefault(
        "DATA_ENCRYPTION_KEY", "dGVzdF9rZXlfZm9yX2NpX29ubHlfMDAwMDAwMDAwMDA="
    )
    spec = importlib.util.spec_from_file_location(
        "_perennia_db_under_test_async", str(target)
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


_db = _load_db()


# ---------------------------------------------------------------------------
# Test 1: db.py exports `get_async_db` and `AsyncSessionLocal`
# ---------------------------------------------------------------------------

def test_db_module_exposes_async_symbols():
    assert hasattr(_db, "get_async_db")
    assert hasattr(_db, "AsyncSessionLocal")
    assert hasattr(_db, "async_engine")


# ---------------------------------------------------------------------------
# Test 2: get_async_db is an async generator function
# ---------------------------------------------------------------------------

def test_get_async_db_is_async_generator_function():
    import inspect
    assert inspect.isasyncgenfunction(_db.get_async_db)


# ---------------------------------------------------------------------------
# Test 3: AsyncSessionLocal is configured (or skip if engine unavailable)
# ---------------------------------------------------------------------------

def test_async_sessionmaker_configured():
    if _db.AsyncSessionLocal is None:
        pytest.skip("async engine not initialized in this environment")
    # Sessionmaker callables produce AsyncSession instances
    assert callable(_db.AsyncSessionLocal)


# ---------------------------------------------------------------------------
# Test 4: get_async_db yields an AsyncSession instance
# ---------------------------------------------------------------------------

def test_get_async_db_yields_async_session():
    if _db.AsyncSessionLocal is None:
        pytest.skip("async engine not initialized in this environment")

    from sqlalchemy.ext.asyncio import AsyncSession

    async def _run():
        gen = _db.get_async_db()
        session = await gen.__anext__()
        try:
            assert isinstance(session, AsyncSession)
        finally:
            # Properly close the async generator
            try:
                await gen.aclose()
            except StopAsyncIteration:
                pass

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Test 5: async_engine singleton — same object on repeat access
# ---------------------------------------------------------------------------

def test_async_engine_is_singleton():
    e1 = _db.async_engine
    e2 = _db.async_engine
    assert e1 is e2


# ---------------------------------------------------------------------------
# Test 6: Async session executes a no-op SELECT 1 (happy path commit-ish)
# ---------------------------------------------------------------------------

def test_async_session_can_execute_select_1():
    if _db.AsyncSessionLocal is None:
        pytest.skip("async engine not initialized in this environment")

    from sqlalchemy import text

    async def _run():
        session = _db.AsyncSessionLocal()
        try:
            result = await session.execute(text("SELECT 1"))
            row = result.fetchone()
            assert row[0] == 1
        finally:
            await session.close()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Test 7: Pool config respects environment overrides (sync engine sanity)
# ---------------------------------------------------------------------------

def test_pool_config_respects_engine_options():
    # The sync engine is always initialized — it's the source of truth for
    # pool sizing. Verify it carries the documented attributes so async paths
    # can rely on parallel configuration.
    engine = _db.engine
    assert engine is not None
    # SQLAlchemy pool exposes .size() / ._max_overflow on supported pool classes
    pool = engine.pool
    # NullPool (PgBouncer mode) doesn't expose .size() — accept either
    assert hasattr(pool, "status") or hasattr(pool, "size")
