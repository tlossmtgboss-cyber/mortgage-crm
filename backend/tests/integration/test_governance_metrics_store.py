"""
Extended integration tests for the governance metrics store.

These tests use the importlib-spec pattern to load the store without pulling
in `agents/__init__.py` (which would drag in langgraph).
"""
from __future__ import annotations

import importlib.util
import sys
import threading
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


_BACKEND_DIR = Path(__file__).resolve().parents[2]


def _load_store():
    target = _BACKEND_DIR / "agents" / "orchestration" / "governance_metrics.py"
    if not target.exists():
        pytest.skip("governance_metrics.py missing")
    spec = importlib.util.spec_from_file_location(
        "_perennia_governance_metrics_store", str(target)
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


_gm = _load_store()
GovernanceMetricsStore = _gm.GovernanceMetricsStore


@pytest.fixture
def store():
    return GovernanceMetricsStore()


# ---------------------------------------------------------------------------
# Record & retrieve — three event classes
# ---------------------------------------------------------------------------

def test_record_compliance_event_appends_to_recent(store):
    store.record_compliance_event("a1", "lead_nurturer", 1, [{"rule": "x"}], False)
    assert len(store.recent_compliance(50)) == 1


def test_record_hallucination_event_appends_to_recent(store):
    store.record_hallucination_event("a1", "rate_advisor", 0.8, ["6%"])
    assert len(store.recent_hallucinations(50)) == 1


def test_record_token_event_appends_to_recent(store):
    store.record_token_usage("a1", "scribe", 100, 200, model="claude-sonnet")
    assert len(store.recent_tokens(50)) == 1


# ---------------------------------------------------------------------------
# Deque bounded at 1000
# ---------------------------------------------------------------------------

def test_buffer_bounded_at_1000(store):
    for i in range(1100):
        store.record_compliance_event(f"agent_{i % 5}", "role", 0, [], False)
    # Newest 1000 retained
    assert len(store._compliance_events) == 1000


# ---------------------------------------------------------------------------
# Thread-safety under concurrent writes
# ---------------------------------------------------------------------------

def test_thread_safe_concurrent_writes(store):
    def writer():
        for _ in range(100):
            store.record_token_usage("a1", "scribe", 1, 1)

    threads = [threading.Thread(target=writer) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # 8 threads * 100 writes = 800 events
    assert store._token_call_count["a1"] == 800


# ---------------------------------------------------------------------------
# Per-agent aggregation
# ---------------------------------------------------------------------------

def test_per_agent_summary_returns_keyed_counters(store):
    store.record_compliance_event("agent_x", "role_y", 3, [], True)
    store.record_hallucination_event("agent_x", "role_y", 0.5, ["c1"])
    summary = store.get_per_agent_summary("agent_x")
    assert summary["agent_id"] == "agent_x"
    assert summary["compliance"]["event_count"] == 1
    assert summary["compliance"]["escalation_count"] == 1
    assert summary["hallucination"]["event_count"] == 1


# ---------------------------------------------------------------------------
# Fleet aggregation rolls up across agents
# ---------------------------------------------------------------------------

def test_fleet_summary_aggregates_across_agents(store):
    store.record_compliance_event("a1", "r1", 1, [], False)
    store.record_compliance_event("a2", "r1", 2, [], True)
    store.record_compliance_event("a3", "r2", 1, [], False)
    fleet = store.get_fleet_summary()
    assert fleet["agent_count"] == 3
    assert fleet["totals"]["compliance_events"] == 3
    assert fleet["totals"]["compliance_violations"] == 4


# ---------------------------------------------------------------------------
# Recent-N retrieval honors the limit
# ---------------------------------------------------------------------------

def test_recent_limit_honors_count(store):
    for i in range(20):
        store.record_compliance_event("a1", "r1", i, [], False)
    assert len(store.recent_compliance(limit=5)) == 5


# ---------------------------------------------------------------------------
# Clear-on-restart caveat (reset() wipes state)
# ---------------------------------------------------------------------------

def test_reset_clears_all_state(store):
    store.record_compliance_event("a1", "r1", 1, [], False)
    store.record_hallucination_event("a1", "r1", 0.5, ["x"])
    store.record_token_usage("a1", "r1", 10, 20)
    store.reset()
    assert store.recent_compliance(50) == []
    assert store.recent_hallucinations(50) == []
    assert store.recent_tokens(50) == []
    # Caveat: in-memory only — confirms the documented behavior.
    assert store._compliance_count.get("a1", 0) == 0


# ---------------------------------------------------------------------------
# Singleton presence — module exposes governance_metrics
# ---------------------------------------------------------------------------

def test_module_exposes_singleton():
    assert hasattr(_gm, "governance_metrics")
    assert isinstance(_gm.governance_metrics, GovernanceMetricsStore)
