"""Integration tests for SharedContextStore (Wave 6 Slice E)."""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from agents.orchestration.shared_context import (  # noqa: E402
    MAX_ENTRIES_PER_CONVERSATION,
    SharedContextStore,
)


@pytest.fixture
def store() -> SharedContextStore:
    return SharedContextStore()


@pytest.mark.asyncio
async def test_set_and_get_round_trip(store: SharedContextStore) -> None:
    await store.set("conv-1", "dti_ratio", 0.42)
    assert await store.get("conv-1", "dti_ratio") == 0.42

    # Replacement semantics.
    await store.set("conv-1", "dti_ratio", 0.45)
    assert await store.get("conv-1", "dti_ratio") == 0.45


@pytest.mark.asyncio
async def test_ttl_expiration(store: SharedContextStore) -> None:
    await store.set("conv-1", "ephemeral", "soon-gone", ttl_seconds=1)
    assert await store.get("conv-1", "ephemeral") == "soon-gone"
    # Force expiry without waiting a full second by patching the stored expiry.
    async with store._lock:
        value, _ = store._store[("conv-1", "ephemeral")]
        store._store[("conv-1", "ephemeral")] = (value, time.time() - 1)
    assert await store.get("conv-1", "ephemeral") is None


@pytest.mark.asyncio
async def test_delete_removes_entry(store: SharedContextStore) -> None:
    await store.set("conv-1", "k", "v")
    assert await store.get("conv-1", "k") == "v"
    await store.delete("conv-1", "k")
    assert await store.get("conv-1", "k") is None
    # No-op on missing key shouldn't raise.
    await store.delete("conv-1", "k")


@pytest.mark.asyncio
async def test_get_all_returns_full_dict(store: SharedContextStore) -> None:
    await store.set("conv-1", "a", 1)
    await store.set("conv-1", "b", 2)
    await store.set("conv-1", "c", 3)
    snapshot = await store.get_all("conv-1")
    assert snapshot == {"a": 1, "b": 2, "c": 3}


@pytest.mark.asyncio
async def test_purge_expired_removes_only_expired(store: SharedContextStore) -> None:
    await store.set("conv-1", "fresh", "alive", ttl_seconds=3600)
    await store.set("conv-1", "stale", "dead", ttl_seconds=1)
    # Force the stale entry's expiry into the past.
    async with store._lock:
        value, _ = store._store[("conv-1", "stale")]
        store._store[("conv-1", "stale")] = (value, time.time() - 10)
    removed = await store.purge_expired()
    assert removed == 1
    assert await store.get("conv-1", "fresh") == "alive"
    assert await store.get("conv-1", "stale") is None


@pytest.mark.asyncio
async def test_concurrent_writes_are_thread_safe(store: SharedContextStore) -> None:
    async def writer(idx: int) -> None:
        await store.set("conv-x", f"key_{idx}", idx)

    await asyncio.gather(*(writer(i) for i in range(200)))
    snapshot = await store.get_all("conv-x")
    assert len(snapshot) == 200
    for i in range(200):
        assert snapshot[f"key_{i}"] == i


@pytest.mark.asyncio
async def test_conversations_are_isolated(store: SharedContextStore) -> None:
    await store.set("conv-a", "shared_key", "from-a")
    await store.set("conv-b", "shared_key", "from-b")
    assert await store.get("conv-a", "shared_key") == "from-a"
    assert await store.get("conv-b", "shared_key") == "from-b"
    # get_all is scoped per conversation.
    assert await store.get_all("conv-a") == {"shared_key": "from-a"}
    assert await store.get_all("conv-b") == {"shared_key": "from-b"}


@pytest.mark.asyncio
async def test_memory_bounded_under_heavy_load(store: SharedContextStore) -> None:
    # Write 200 distinct keys; the cap is much larger so all should fit.
    for i in range(200):
        await store.set("conv-load", f"k{i}", i)
    snapshot = await store.get_all("conv-load")
    assert len(snapshot) == 200
    # Conversation index must never exceed the documented cap.
    async with store._lock:
        assert len(store._by_conversation["conv-load"]) <= MAX_ENTRIES_PER_CONVERSATION
