"""
WebSocket Session Manager (CQ-006 fix)
======================================

Central in-memory registry for active WebSocket sessions across the platform.

Replaces ad-hoc per-route `active_connections = {}` dictionaries that historically
leaked memory when a `WebSocketDisconnect` was raised in a non-obvious code path
(e.g. inside `await websocket.send_json` after the peer dropped).

Key design points
-----------------
* **Thread-safe** via `asyncio.Lock`; safe to call from concurrent coroutines.
* **Idle timeout** – sessions with no recorded activity within
  `WS_IDLE_TIMEOUT_SECONDS` (default 900s = 15 min) are pruned automatically by
  the background sweeper.
* **Sweeper** – `start_sweeper()` schedules a coroutine that calls
  `prune_stale()` every 5 minutes. Safe to call multiple times; only one task
  is ever started.
* **Backward compatible** – existing routes that maintain their own dicts keep
  working. They can opt in by registering with this manager in addition to (or
  instead of) their local bookkeeping.

Usage
-----
    from backend.services.websocket_session_manager import ws_session_manager

    await ws_session_manager.register(session_id, websocket, {"call_id": call_id})
    try:
        ...
    finally:
        await ws_session_manager.unregister(session_id)
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

WS_IDLE_TIMEOUT_SECONDS: int = int(os.getenv("WS_IDLE_TIMEOUT_SECONDS", "900"))
WS_SWEEP_INTERVAL_SECONDS: int = int(os.getenv("WS_SWEEP_INTERVAL_SECONDS", "300"))


# ---------------------------------------------------------------------------
# Session record
# ---------------------------------------------------------------------------

@dataclass
class WebSocketSession:
    session_id: str
    websocket: Any  # fastapi.WebSocket — typed as Any to avoid hard import
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    last_activity_at: float = field(default_factory=time.time)

    def touch(self) -> None:
        """Mark the session as active (used to extend idle timeout)."""
        self.last_activity_at = time.time()

    def age_seconds(self) -> float:
        return time.time() - self.created_at

    def idle_seconds(self) -> float:
        return time.time() - self.last_activity_at


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------

class WebSocketSessionManager:
    """Process-wide registry of live WebSocket sessions."""

    def __init__(self) -> None:
        self._sessions: Dict[str, WebSocketSession] = {}
        self._lock = asyncio.Lock()
        self._sweeper_task: Optional[asyncio.Task] = None
        self._stopped = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def register(
        self,
        session_id: str,
        websocket: Any,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> WebSocketSession:
        """Register a new live session. Overwrites any prior session with the same id."""
        async with self._lock:
            session = WebSocketSession(
                session_id=session_id,
                websocket=websocket,
                metadata=dict(metadata or {}),
            )
            self._sessions[session_id] = session
            logger.debug(
                "WS session registered: id=%s active=%d", session_id, len(self._sessions)
            )
            return session

    async def unregister(self, session_id: str) -> bool:
        """Remove a session from the registry. Returns True if removed."""
        async with self._lock:
            existed = self._sessions.pop(session_id, None) is not None
            if existed:
                logger.debug(
                    "WS session unregistered: id=%s active=%d",
                    session_id,
                    len(self._sessions),
                )
            return existed

    async def touch(self, session_id: str) -> bool:
        """Update last_activity_at for an existing session."""
        async with self._lock:
            sess = self._sessions.get(session_id)
            if sess is None:
                return False
            sess.touch()
            return True

    def get(self, session_id: str) -> Optional[WebSocketSession]:
        """Lookup without acquiring the lock (read-only snapshot)."""
        return self._sessions.get(session_id)

    def get_active_count(self) -> int:
        return len(self._sessions)

    def list_sessions(self) -> List[WebSocketSession]:
        return list(self._sessions.values())

    async def prune_stale(
        self, max_age_seconds: Optional[int] = None
    ) -> List[str]:
        """Drop sessions whose idle time exceeds `max_age_seconds`.

        Returns the list of session_ids that were pruned.
        """
        threshold = (
            max_age_seconds
            if max_age_seconds is not None
            else WS_IDLE_TIMEOUT_SECONDS
        )
        pruned: List[str] = []
        async with self._lock:
            now = time.time()
            for sid, sess in list(self._sessions.items()):
                if now - sess.last_activity_at > threshold:
                    pruned.append(sid)
                    self._sessions.pop(sid, None)
        for sid in pruned:
            logger.info("WS session pruned (idle): id=%s", sid)
        return pruned

    # ------------------------------------------------------------------
    # Background sweeper
    # ------------------------------------------------------------------

    async def _sweep_loop(self) -> None:
        logger.info(
            "WS sweeper started: idle_timeout=%ds interval=%ds",
            WS_IDLE_TIMEOUT_SECONDS,
            WS_SWEEP_INTERVAL_SECONDS,
        )
        while not self._stopped:
            try:
                await asyncio.sleep(WS_SWEEP_INTERVAL_SECONDS)
                await self.prune_stale()
            except asyncio.CancelledError:
                break
            except Exception as exc:  # pragma: no cover - defensive
                logger.exception("WS sweeper error: %s", exc)

    def start_sweeper(self) -> None:
        """Idempotently start the periodic sweeper task.

        Safe to call from FastAPI startup or wherever an event loop is running.
        If no running loop is available, this is a no-op (the sweeper can be
        started later).
        """
        if self._sweeper_task is not None and not self._sweeper_task.done():
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.debug("No running event loop; sweeper not started")
            return
        self._stopped = False
        self._sweeper_task = loop.create_task(self._sweep_loop())

    async def stop_sweeper(self) -> None:
        self._stopped = True
        task = self._sweeper_task
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        self._sweeper_task = None


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

ws_session_manager = WebSocketSessionManager()


__all__ = [
    "WS_IDLE_TIMEOUT_SECONDS",
    "WS_SWEEP_INTERVAL_SECONDS",
    "WebSocketSession",
    "WebSocketSessionManager",
    "ws_session_manager",
]
