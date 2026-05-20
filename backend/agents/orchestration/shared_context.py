"""
SharedContextStore — Cross-agent ephemeral key/value layer.

Wave 6 / Slice E. Multiple agents in the same conversation (orchestrator
+ specialised tools + receptionist hand-off) need to share intermediate
findings — e.g. the underwriter agent computes a DTI ratio that the
compliance agent then references. Re-deriving in each agent wastes
tokens and risks divergent answers. This store gives them a thin,
TTL-bounded, conversation-scoped scratchpad.

Storage
-------
In-memory ``dict`` keyed by ``(conversation_id, key)`` mapping to
``(value, expiry_epoch)``. An ``asyncio.Lock`` guards mutations so
concurrent ``asyncio.gather`` calls inside a single event loop see
consistent state.

Per-conversation safety cap: ``MAX_ENTRIES_PER_CONVERSATION = 10000``.
When the cap is hit the oldest expiring entry for that conversation is
evicted before the new write succeeds (keeps the store memory-bounded
under accidental write storms).

Production note
---------------
For multi-worker / multi-replica deployments this should sit behind
Redis (or Postgres-backed agent_shared_context table) so context
survives worker recycling and is visible across replicas. The in-memory
implementation is a v1 fit for single-worker Railway deploys.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


DEFAULT_TTL_SECONDS = 3600  # 1 hour
PURGE_INTERVAL_SECONDS = 300  # background sweep every 5 min
MAX_ENTRIES_PER_CONVERSATION = 10000


class SharedContextStore:
    """Thread/coroutine-safe ephemeral context store for cross-agent sharing."""

    def __init__(self) -> None:
        # (conversation_id, key) -> (value, expiry_epoch)
        self._store: Dict[Tuple[str, str], Tuple[Any, float]] = {}
        # conversation_id -> set of keys (cheap per-conversation index)
        self._by_conversation: Dict[str, set] = defaultdict(set)
        self._lock = asyncio.Lock()
        self._purge_task: Optional[asyncio.Task] = None

    # ------------------------------------------------------------------ core

    async def set(
        self,
        conversation_id: str,
        key: str,
        value: Any,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
    ) -> None:
        """Insert/replace a value, scoped to ``conversation_id``, with TTL."""
        ttl = int(ttl_seconds) if ttl_seconds and ttl_seconds > 0 else DEFAULT_TTL_SECONDS
        expiry = time.time() + ttl
        conv = str(conversation_id)
        async with self._lock:
            keys_for_conv = self._by_conversation[conv]

            # Memory cap: if we're at the per-conversation ceiling and this
            # is a new key, evict the soonest-to-expire entry first.
            if (conv, key) not in self._store and len(keys_for_conv) >= MAX_ENTRIES_PER_CONVERSATION:
                victim_key = None
                victim_expiry = float("inf")
                for k in keys_for_conv:
                    _, exp = self._store.get((conv, k), (None, 0.0))
                    if exp < victim_expiry:
                        victim_expiry = exp
                        victim_key = k
                if victim_key is not None:
                    self._store.pop((conv, victim_key), None)
                    keys_for_conv.discard(victim_key)

            self._store[(conv, key)] = (value, expiry)
            keys_for_conv.add(key)

    async def get(self, conversation_id: str, key: str) -> Any:
        """Return the value if present and not expired, else ``None``."""
        conv = str(conversation_id)
        async with self._lock:
            entry = self._store.get((conv, key))
            if entry is None:
                return None
            value, expiry = entry
            if expiry < time.time():
                # Lazy expiration on read.
                self._store.pop((conv, key), None)
                self._by_conversation[conv].discard(key)
                return None
            return value

    async def get_all(self, conversation_id: str) -> Dict[str, Any]:
        """Return all non-expired entries for ``conversation_id``."""
        conv = str(conversation_id)
        now = time.time()
        out: Dict[str, Any] = {}
        async with self._lock:
            keys = list(self._by_conversation.get(conv, ()))
            for k in keys:
                entry = self._store.get((conv, k))
                if entry is None:
                    self._by_conversation[conv].discard(k)
                    continue
                value, expiry = entry
                if expiry < now:
                    self._store.pop((conv, k), None)
                    self._by_conversation[conv].discard(k)
                    continue
                out[k] = value
        return out

    async def delete(self, conversation_id: str, key: str) -> None:
        """Remove a single key (no-op if absent)."""
        conv = str(conversation_id)
        async with self._lock:
            self._store.pop((conv, key), None)
            self._by_conversation[conv].discard(key)

    async def purge_expired(self) -> int:
        """Sweep and drop all expired entries. Returns the count removed."""
        now = time.time()
        removed = 0
        async with self._lock:
            to_drop = [
                (conv, key)
                for (conv, key), (_, expiry) in self._store.items()
                if expiry < now
            ]
            for conv, key in to_drop:
                self._store.pop((conv, key), None)
                self._by_conversation[conv].discard(key)
                removed += 1
        if removed:
            logger.debug("SharedContextStore: purged %d expired entries", removed)
        return removed

    # --------------------------------------------------- background sweeper

    def start_background_purge(self) -> None:
        """Kick off the periodic purge task. Idempotent."""
        if self._purge_task is not None and not self._purge_task.done():
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No loop yet — caller can re-invoke once one exists.
            return
        self._purge_task = loop.create_task(self._purge_loop())

    async def _purge_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(PURGE_INTERVAL_SECONDS)
                await self.purge_expired()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.warning("SharedContextStore purge loop error: %s", exc)


# Module-level singleton.
shared_context = SharedContextStore()


__all__ = [
    "SharedContextStore",
    "shared_context",
    "DEFAULT_TTL_SECONDS",
    "MAX_ENTRIES_PER_CONVERSATION",
]
