"""
Integration tests for the Wave 3 in-process governance metrics store.

Loads ``agents/orchestration/governance_metrics.py`` by file path so the
heavy ``agents/__init__.py`` (which pulls in langgraph + the full agent
fleet) is never imported. Matches the Wave 2 integration test discipline
established in ``test_compliance_guard.py``.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


def _load_governance_metrics():
    backend_dir = Path(__file__).resolve().parents[2]
    target = backend_dir / "agents" / "orchestration" / "governance_metrics.py"
    if not target.exists():  # pragma: no cover - safety net
        pytest.skip(f"governance_metrics.py not found at {target}")
    spec = importlib.util.spec_from_file_location(
        "_perennia_governance_metrics_under_test", str(target)
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


_gm_module = _load_governance_metrics()
GovernanceMetricsStore = _gm_module.GovernanceMetricsStore


@pytest.fixture
def store() -> "GovernanceMetricsStore":
    """Fresh store per test — singleton not used here for isolation."""
    return GovernanceMetricsStore()


# ---------------------------------------------------------------------------
# 1. Record + retrieve compliance event
# ---------------------------------------------------------------------------

def test_record_and_retrieve_compliance_event(store):
    store.record_compliance_event(
        agent_id="lead_nurturer",
        agent_role="lead_nurturer",
        violation_count=2,
        violations=[
            {"regulation": "TRID", "rule": "apr_without_disclosure", "severity": "hard_block"},
            {"regulation": "ECOA", "rule": "prohibited_basis", "severity": "hard_block"},
        ],
        escalated=True,
    )
    recent = store.recent_compliance(limit=10)
    assert len(recent) == 1
    evt = recent[0]
    assert evt["agent_id"] == "lead_nurturer"
    assert evt["agent_role"] == "lead_nurturer"
    assert evt["violation_count"] == 2
    assert evt["escalated"] is True
    assert len(evt["violations"]) == 2


# ---------------------------------------------------------------------------
# 2. Record + retrieve hallucination event
# ---------------------------------------------------------------------------

def test_record_and_retrieve_hallucination_event(store):
    store.record_hallucination_event(
        agent_id="rate_advisor",
        agent_role="rate_advisor",
        confidence=0.5,
        unverified_claims=["6.5%", "$250k"],
    )
    recent = store.recent_hallucinations(limit=10)
    assert len(recent) == 1
    evt = recent[0]
    assert evt["agent_id"] == "rate_advisor"
    assert evt["confidence"] == 0.5
    assert evt["unverified_count"] == 2
    assert "6.5%" in evt["unverified_claims"]


# ---------------------------------------------------------------------------
# 3. Record + retrieve token usage
# ---------------------------------------------------------------------------

def test_record_and_retrieve_token_usage(store):
    store.record_token_usage(
        agent_id="pipeline_analyst",
        agent_role="pipeline_analyst",
        input_tokens=400,
        output_tokens=120,
        model="claude-sonnet",
    )
    recent = store.recent_tokens(limit=10)
    assert len(recent) == 1
    evt = recent[0]
    assert evt["agent_id"] == "pipeline_analyst"
    assert evt["input_tokens"] == 400
    assert evt["output_tokens"] == 120
    assert evt["total_tokens"] == 520
    assert evt["model"] == "claude-sonnet"


# ---------------------------------------------------------------------------
# 4. Per-agent summary aggregates correctly
# ---------------------------------------------------------------------------

def test_per_agent_summary_aggregates_correctly(store):
    aid = "compliance_checker"
    role = "compliance_checker"

    # Two compliance events (one escalated), three token calls,
    # two hallucination checks.
    store.record_compliance_event(aid, role, violation_count=1,
                                  violations=[{"rule": "best_rate_no_disclaimer"}],
                                  escalated=False)
    store.record_compliance_event(aid, role, violation_count=3,
                                  violations=[{"rule": "guaranteed_approval"}],
                                  escalated=True)

    store.record_hallucination_event(aid, role, confidence=0.8, unverified_claims=["5%"])
    store.record_hallucination_event(aid, role, confidence=0.6, unverified_claims=["$1k", "$2k"])

    store.record_token_usage(aid, role, 100, 50)
    store.record_token_usage(aid, role, 200, 75)
    store.record_token_usage(aid, role, 50, 25)

    summary = store.get_per_agent_summary(aid, last_n=10)
    assert summary["agent_id"] == aid
    assert summary["agent_role"] == role

    comp = summary["compliance"]
    assert comp["event_count"] == 2
    assert comp["violation_count"] == 4  # 1 + 3
    assert comp["escalation_count"] == 1
    assert len(comp["recent"]) == 2

    hall = summary["hallucination"]
    assert hall["event_count"] == 2
    assert hall["unverified_total"] == 3  # 1 + 2
    # mean of 0.8 and 0.6
    assert hall["avg_confidence"] == pytest.approx(0.7, abs=1e-6)

    tok = summary["tokens"]
    assert tok["call_count"] == 3
    assert tok["input_total"] == 350
    assert tok["output_total"] == 150
    assert tok["grand_total"] == 500


# ---------------------------------------------------------------------------
# 5. Fleet summary roll-up correct (per-role totals + hot-spots)
# ---------------------------------------------------------------------------

def test_fleet_summary_rollup_correct(store):
    # Three agents across two roles.
    store.record_compliance_event("a1", "lead_nurturer", violation_count=5,
                                  violations=[], escalated=True)
    store.record_compliance_event("a2", "lead_nurturer", violation_count=1,
                                  violations=[], escalated=False)
    store.record_compliance_event("b1", "rate_advisor", violation_count=2,
                                  violations=[], escalated=False)

    store.record_hallucination_event("a1", "lead_nurturer",
                                     confidence=0.4, unverified_claims=["x", "y", "z"])
    store.record_hallucination_event("b1", "rate_advisor",
                                     confidence=0.9, unverified_claims=["q"])

    store.record_token_usage("a1", "lead_nurturer", 1000, 500)
    store.record_token_usage("a2", "lead_nurturer", 100, 50)
    store.record_token_usage("b1", "rate_advisor", 300, 100)

    fleet = store.get_fleet_summary(top_n=2)

    assert fleet["agent_count"] == 3

    totals = fleet["totals"]
    assert totals["compliance_events"] == 3
    assert totals["compliance_violations"] == 8  # 5+1+2
    assert totals["compliance_escalations"] == 1
    assert totals["hallucination_events"] == 2
    assert totals["unverified_claims"] == 4  # 3+1
    assert totals["token_calls"] == 3
    assert totals["input_tokens"] == 1400  # 1000+100+300
    assert totals["output_tokens"] == 650  # 500+50+100

    per_role = fleet["per_role"]
    assert "lead_nurturer" in per_role
    assert "rate_advisor" in per_role
    ln = per_role["lead_nurturer"]
    assert ln["agents"] == 2
    assert ln["compliance_violations"] == 6  # 5+1
    assert ln["token_calls"] == 2
    assert ln["input_tokens"] == 1100
    assert ln["output_tokens"] == 550

    ra = per_role["rate_advisor"]
    assert ra["agents"] == 1
    assert ra["compliance_violations"] == 2

    hot = fleet["hot_spots"]
    # a1 had 5 compliance violations — should be top of the compliance hot-spot
    assert hot["compliance"][0]["agent_id"] == "a1"
    # a1 also has the largest token spend (1500)
    assert hot["tokens"][0]["agent_id"] == "a1"
    assert hot["tokens"][0]["total_tokens"] == 1500
    # a1 had 3 unverified claims — top of hallucination hot-spot
    assert hot["hallucination"][0]["agent_id"] == "a1"
