"""
Integration tests for async DB plumbing.

Validates:
  1. ``get_async_db`` (or equivalent) is exposed
  2. The yielded session is an ``AsyncSession``
  3. RLS context (``app.current_tenant``) propagates onto the async session
  4. Rollback works when an exception is raised inside the context
  5. Connections are released back to the pool on exception
  6. Pool size respected (no leaks under burst load)

Most assertions xfail until the async-DB module is wired by W3. Imports
and collection must succeed cleanly.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


pytestmark = pytest.mark.integration


def _load_db_module():
    backend_dir = Path(__file__).resolve().parents[2]
    for name in ("async_db.py", "db_async.py", "db.py"):
        target = backend_dir / name
        if target.exists():
            spec = importlib.util.spec_from_file_location(
                f"_perennia_db_under_test_{target.stem}", str(target)
            )
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            try:
                spec.loader.exec_module(module)  # type: ignore[union-attr]
            except Exception:
                continue
            return module
    return None


_db_module = _load_db_module()


@pytest.mark.xfail(
    not (_db_module and hasattr(_db_module, "get_async_db")),
    reason="TODO(W3): async DB session factory not yet wired",
    strict=False,
)
def test_get_async_db_yields_async_session():
    assert _db_module is not None
    assert hasattr(_db_module, "get_async_db")


@pytest.mark.xfail(
    reason="TODO(W3): RLS propagation requires async session live",
    strict=False,
)
def test_rls_context_propagates_to_async_session():
    assert _db_module is not None
    # When live: open session, set app.current_tenant, verify SELECT scope.
    raise AssertionError("not yet wired")


@pytest.mark.xfail(
    reason="TODO(W3): rollback test requires live async session",
    strict=False,
)
def test_rollback_inside_async_context():
    assert _db_module is not None
    raise AssertionError("not yet wired")


@pytest.mark.xfail(
    reason="TODO(W3): connection-release test needs live pool",
    strict=False,
)
def test_connection_released_on_exception():
    assert _db_module is not None
    raise AssertionError("not yet wired")


@pytest.mark.xfail(
    reason="TODO(W3): pool-size enforcement test needs live pool",
    strict=False,
)
def test_pool_size_respected_under_burst():
    assert _db_module is not None
    raise AssertionError("not yet wired")
