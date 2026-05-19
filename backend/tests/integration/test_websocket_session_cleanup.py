"""
Integration tests for the central WebSocket session manager (CQ-006).

Validates that registration / deregistration round-trips, disconnect cleanup,
idle-timeout pruning, and active-count tracking all behave correctly.
"""
from __future__ import annotations

import asyncio
import time

import pytest

from services.websocket_session_manager import (
    WebSocketSessionManager,
    ws_session_manager,
)


class FakeWebSocket:
    """Minimal stand-in for fastapi.WebSocket — only the identity matters."""

    def __init__(self, name: str = "ws"):
        self.name = name
        self.closed = False

    async def close(self, code: int = 1000, reason: str = ""):
        self.closed = True


def _run(coro):
    """Helper to run a coroutine in the current event loop or a fresh one."""
    return asyncio.get_event_loop().run_until_complete(coro) if False else asyncio.run(coro)


# ---------------------------------------------------------------------------
# 1. Register + unregister round-trip
# ---------------------------------------------------------------------------

def test_register_and_unregister_round_trip():
    mgr = WebSocketSessionManager()
    ws = FakeWebSocket("a")

    async def scenario():
        await mgr.register("sess-1", ws, {"call_id": "call-1"})
        assert mgr.get_active_count() == 1
        sess = mgr.get("sess-1")
        assert sess is not None
        assert sess.metadata["call_id"] == "call-1"

        removed = await mgr.unregister("sess-1")
        assert removed is True
        assert mgr.get_active_count() == 0
        assert mgr.get("sess-1") is None

    asyncio.run(scenario())


# ---------------------------------------------------------------------------
# 2. Disconnect triggers unregister (simulated via finally-block contract)
# ---------------------------------------------------------------------------

def test_disconnect_triggers_unregister():
    """Simulate the finally-block pattern enforced in WS endpoints."""
    mgr = WebSocketSessionManager()
    ws = FakeWebSocket("b")

    async def scenario():
        await mgr.register("sess-disconnect", ws, {})
        assert mgr.get_active_count() == 1

        # Simulate the endpoint pattern: WebSocketDisconnect raised in try,
        # cleanup runs in finally.
        try:
            raise RuntimeError("simulated WebSocketDisconnect")
        except RuntimeError:
            pass
        finally:
            await mgr.unregister("sess-disconnect")

        assert mgr.get_active_count() == 0

    asyncio.run(scenario())


# ---------------------------------------------------------------------------
# 3. Idle session pruned after timeout
# ---------------------------------------------------------------------------

def test_idle_session_pruned_after_timeout():
    mgr = WebSocketSessionManager()
    ws = FakeWebSocket("c")

    async def scenario():
        sess = await mgr.register("sess-idle", ws, {})
        # Backdate last_activity to simulate idleness.
        sess.last_activity_at = time.time() - 1000  # 1000s in the past

        pruned = await mgr.prune_stale(max_age_seconds=900)
        assert "sess-idle" in pruned
        assert mgr.get_active_count() == 0

    asyncio.run(scenario())


# ---------------------------------------------------------------------------
# 4. prune_stale removes only stale sessions
# ---------------------------------------------------------------------------

def test_prune_stale_removes_only_stale():
    mgr = WebSocketSessionManager()

    async def scenario():
        fresh = await mgr.register("fresh", FakeWebSocket("f"), {})
        stale = await mgr.register("stale", FakeWebSocket("s"), {})
        stale.last_activity_at = time.time() - 5000

        pruned = await mgr.prune_stale(max_age_seconds=900)
        assert pruned == ["stale"]
        assert mgr.get_active_count() == 1
        assert mgr.get("fresh") is not None
        assert mgr.get("stale") is None

    asyncio.run(scenario())


# ---------------------------------------------------------------------------
# 5. get_active_count reflects current state
# ---------------------------------------------------------------------------

def test_get_active_count_reflects_state():
    mgr = WebSocketSessionManager()

    async def scenario():
        assert mgr.get_active_count() == 0
        await mgr.register("a", FakeWebSocket(), {})
        await mgr.register("b", FakeWebSocket(), {})
        await mgr.register("c", FakeWebSocket(), {})
        assert mgr.get_active_count() == 3

        await mgr.unregister("b")
        assert mgr.get_active_count() == 2

        await mgr.unregister("missing")  # no-op
        assert mgr.get_active_count() == 2

    asyncio.run(scenario())


# ---------------------------------------------------------------------------
# Sanity: module-level singleton exists and is a manager instance
# ---------------------------------------------------------------------------

def test_module_singleton_exists():
    assert isinstance(ws_session_manager, WebSocketSessionManager)
