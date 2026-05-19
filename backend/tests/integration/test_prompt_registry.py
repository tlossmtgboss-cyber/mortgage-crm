"""
Integration tests for the prompt registry (Wave 5, D3 audit).

Covers:
1. register stores a new prompt with hash + metadata
2. get(version=specific) returns that version
3. get(version=None) returns the current/latest
4. list_versions returns history oldest-first
5. rollback flips current pointer
6. hash dedup — same content → same record (idempotent)
7. concurrent writes don't corrupt the file
8. file format on disk (JSON dict of prompt_id → list of records)

Loaded via importlib spec to avoid the ``agents/__init__.py`` langgraph chain.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import threading
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


_BACKEND_DIR = Path(__file__).resolve().parents[2]


def _load_module():
    target = _BACKEND_DIR / "agents" / "orchestration" / "prompt_registry.py"
    if not target.exists():
        pytest.skip("prompt_registry.py missing")
    spec = importlib.util.spec_from_file_location(
        "_perennia_prompt_registry_test", str(target)
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


_pr = _load_module()
PromptRegistry = _pr.PromptRegistry


@pytest.fixture
def registry(tmp_path):
    store = tmp_path / "prompts_registry.json"
    return PromptRegistry(store_path=store), store


# ---------------------------------------------------------------------------
# 1. register stores new prompt
# ---------------------------------------------------------------------------

def test_register_stores_new_prompt(registry):
    reg, _ = registry
    rec = reg.register("aria.system", "1.0.0", "Hello, this is Aria.",
                       metadata={"author": "alex"})
    assert rec["version"] == "1.0.0"
    assert rec["is_current"] is True
    assert rec["content_hash"]
    assert rec["metadata"]["author"] == "alex"


# ---------------------------------------------------------------------------
# 2. get(version=specific)
# ---------------------------------------------------------------------------

def test_get_specific_version(registry):
    reg, _ = registry
    reg.register("p1", "1.0.0", "first")
    reg.register("p1", "1.1.0", "second")
    v1 = reg.get("p1", "1.0.0")
    assert v1 is not None
    assert v1["content"] == "first"
    assert v1["version"] == "1.0.0"


# ---------------------------------------------------------------------------
# 3. get(version=None) returns latest/current
# ---------------------------------------------------------------------------

def test_get_latest_returns_current(registry):
    reg, _ = registry
    reg.register("p1", "1.0.0", "first")
    reg.register("p1", "1.1.0", "second")
    latest = reg.get("p1", None)
    assert latest is not None
    assert latest["version"] == "1.1.0"
    assert latest["is_current"] is True


# ---------------------------------------------------------------------------
# 4. list_versions ordering
# ---------------------------------------------------------------------------

def test_list_versions_oldest_first(registry):
    reg, _ = registry
    reg.register("p1", "1.0.0", "a")
    reg.register("p1", "2.0.0", "b")
    reg.register("p1", "1.5.0", "c")
    versions = [r["version"] for r in reg.list_versions("p1")]
    assert versions == ["1.0.0", "1.5.0", "2.0.0"]


# ---------------------------------------------------------------------------
# 5. rollback flips current pointer
# ---------------------------------------------------------------------------

def test_rollback_flips_current_pointer(registry):
    reg, _ = registry
    reg.register("p1", "1.0.0", "old")
    reg.register("p1", "2.0.0", "new")
    assert reg.current_version("p1") == "2.0.0"

    rolled = reg.rollback("p1", "1.0.0")
    assert rolled["version"] == "1.0.0"
    assert reg.current_version("p1") == "1.0.0"
    # 2.0.0 should now be deprecated
    v2 = reg.get("p1", "2.0.0")
    assert v2["is_current"] is False
    assert v2["deprecated_at"] is not None


# ---------------------------------------------------------------------------
# 6. hash dedup — same content is idempotent
# ---------------------------------------------------------------------------

def test_register_is_idempotent_on_content_hash(registry):
    reg, _ = registry
    rec1 = reg.register("p1", "1.0.0", "exact same content")
    # Caller tries to bump the version but content didn't change.
    rec2 = reg.register("p1", "1.1.0", "exact same content")
    assert rec2["version"] == rec1["version"]  # got the existing back
    assert len(reg.list_versions("p1")) == 1


# ---------------------------------------------------------------------------
# 7. concurrent writes don't corrupt the file
# ---------------------------------------------------------------------------

def test_concurrent_writes_remain_consistent(tmp_path):
    store = tmp_path / "concurrent.json"
    reg = PromptRegistry(store_path=store)

    errors = []

    def writer(idx: int):
        try:
            # Each thread writes a distinct prompt_id so version conflicts
            # don't matter; the test exercises file-level write contention.
            reg.register(f"p_{idx}", "1.0.0", f"content_{idx}")
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"writer errors: {errors!r}"
    prompts = reg.list_prompts()
    assert len(prompts) == 16
    # File must still be valid JSON
    on_disk = json.loads(store.read_text())
    assert isinstance(on_disk, dict)
    assert len(on_disk) == 16


# ---------------------------------------------------------------------------
# 8. on-disk file format
# ---------------------------------------------------------------------------

def test_file_format_is_dict_of_lists(registry):
    reg, path = registry
    reg.register("formatted_id", "1.0.0", "abc")
    raw = json.loads(path.read_text())
    assert isinstance(raw, dict)
    assert "formatted_id" in raw
    history = raw["formatted_id"]
    assert isinstance(history, list)
    rec = history[0]
    for field in ("version", "content_hash", "content", "metadata",
                  "created_at", "deprecated_at", "is_current"):
        assert field in rec, f"missing field {field!r}"
