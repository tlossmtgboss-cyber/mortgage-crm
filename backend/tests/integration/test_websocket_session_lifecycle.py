"""
Lifecycle tests for `services/websocket_session_manager.py`.
"""
from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


_BACKEND_DIR = Path(__file__).resolve().parents[2]


def _load_mgr():
    target = _BACKEND_DIR / "services" / "websocket_session_manager.py"
    if not target.exists():
        pytest.skip("websocket_session_manager.py missing")
    spec = importlib.util.spec_from_file_location(
        "_perennia_ws_session_lifecycle", str(target)
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


_ws = _load_mgr()
WebSocketSessionManager = _ws.WebSocketSessionManager


def _fresh():
    return WebSocketSessionManager()


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# 1. register
# ---------------------------------------------------------------------------

def test_register_adds_session():
    m = _fresh()
    _run(m.register("s1", object()))
    assert m.get_active_count() == 1


# ---------------------------------------------------------------------------
# 2. unregister
# ---------------------------------------------------------------------------

def test_unregister_removes_session():
    m = _fresh()
    _run(m.register("s1", object()))
    removed = _run(m.unregister("s1"))
    assert removed is True
    assert m.get_active_count() == 0


# ---------------------------------------------------------------------------
# 3. idle prune
# ---------------------------------------------------------------------------

def test_prune_stale_drops_idle_sessions():
    m = _fresh()
    _run(m.register("s1", object()))
    # Force the session to be "old".
    sess = m.get("s1")
    sess.last_activity_at = 0  # epoch — definitely beyond timeout
    pruned = _run(m.prune_stale(max_age_seconds=1))
    assert "s1" in pruned
    assert m.get_active_count() == 0


# ---------------------------------------------------------------------------
# 4. double-register handles gracefully (overwrites)
# ---------------------------------------------------------------------------

def test_double_register_overwrites():
    m = _fresh()
    _run(m.register("s1", object()))
    _run(m.register("s1", object()))
    assert m.get_active_count() == 1


# ---------------------------------------------------------------------------
# 5. unregister then re-register
# ---------------------------------------------------------------------------

def test_unregister_then_register_round_trips():
    m = _fresh()
    _run(m.register("s1", object()))
    _run(m.unregister("s1"))
    _run(m.register("s1", object()))
    assert m.get_active_count() == 1


# ---------------------------------------------------------------------------
# 6. concurrent registers — all retained
# ---------------------------------------------------------------------------

def test_concurrent_registers_all_retained():
    m = _fresh()

    async def runner():
        await asyncio.gather(*(m.register(f"s{i}", object()) for i in range(20)))

    asyncio.new_event_loop().run_until_complete(runner())
    assert m.get_active_count() == 20


# ---------------------------------------------------------------------------
# 7. start_sweeper is a no-op when no event loop is running
# ---------------------------------------------------------------------------

def test_start_sweeper_noop_without_loop():
    m = _fresh()
    # No running loop — start_sweeper should just log + return.
    m.start_sweeper()
    assert m._sweeper_task is None


# ---------------------------------------------------------------------------
# 8. touch updates last_activity_at
# ---------------------------------------------------------------------------

def test_touch_updates_last_activity():
    m = _fresh()
    _run(m.register("s1", object()))
    sess = m.get("s1")
    sess.last_activity_at = 0
    _run(m.touch("s1"))
    assert m.get("s1").last_activity_at > 0


# ---------------------------------------------------------------------------
# 9. get_active_count accurate
# ---------------------------------------------------------------------------

def test_active_count_accurate_after_mixed_ops():
    m = _fresh()
    _run(m.register("a", object()))
    _run(m.register("b", object()))
    _run(m.register("c", object()))
    _run(m.unregister("b"))
    assert m.get_active_count() == 2


# ---------------------------------------------------------------------------
# 10. stop_sweeper safe when sweeper never started
# ---------------------------------------------------------------------------

def test_stop_sweeper_safe_when_not_started():
    m = _fresh()
    _run(m.stop_sweeper())
    assert m._sweeper_task is None
