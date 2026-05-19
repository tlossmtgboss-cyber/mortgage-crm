"""
Integration tests for the per-tool cost dashboard (Wave 5, D3 audit).

Covers:
1. record_tool_call appends per-tool events + bumps counters
2. get_tool_summary aggregates calls, success_rate, latency percentiles
3. get_top_tools_by_cost ranks by total estimated cost
4. pricing math matches _PRICING_PER_1K_TOKENS table
5. admin route auth gate rejects un-authed callers
6. admin route response shape (count + tools array)

The store is loaded via importlib spec to avoid pulling in
``backend/agents/__init__.py`` (which would import langgraph).
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


_BACKEND_DIR = Path(__file__).resolve().parents[2]


def _load_store():
    target = _BACKEND_DIR / "agents" / "orchestration" / "governance_metrics.py"
    if not target.exists():
        pytest.skip("governance_metrics.py missing")
    spec = importlib.util.spec_from_file_location(
        "_perennia_tool_cost_store", str(target)
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


_gm = _load_store()
GovernanceMetricsStore = _gm.GovernanceMetricsStore
_PRICING = _gm._PRICING_PER_1K_TOKENS


@pytest.fixture
def store():
    return GovernanceMetricsStore()


# ---------------------------------------------------------------------------
# 1. record_tool_call writes + counters
# ---------------------------------------------------------------------------

def test_record_tool_call_appends_event_and_bumps_counters(store):
    store.record_tool_call(
        agent_id="agent_a",
        agent_role="pipeline_analyst",
        tool_name="get_pipeline",
        input_tokens=100,
        output_tokens=50,
        model="claude-sonnet-4-6",
        duration_ms=42.5,
        success=True,
    )
    summary = store.get_tool_summary("get_pipeline")
    assert summary["total_calls"] == 1
    assert summary["success_count"] == 1
    assert summary["failure_count"] == 0
    assert summary["total_input_tokens"] == 100
    assert summary["total_output_tokens"] == 50
    assert summary["estimated_cost_usd"] > 0
    assert summary["p50_latency_ms"] == pytest.approx(42.5, rel=1e-3)


# ---------------------------------------------------------------------------
# 2. get_tool_summary success_rate & percentiles
# ---------------------------------------------------------------------------

def test_get_tool_summary_success_rate_and_percentiles(store):
    # 4 successes, 1 failure → success_rate = 0.8
    for ms, ok in [(10.0, True), (20.0, True), (30.0, True), (40.0, True), (100.0, False)]:
        store.record_tool_call(
            agent_id="a",
            agent_role="r",
            tool_name="search_leads",
            input_tokens=10,
            output_tokens=5,
            model="claude-haiku-4-5",
            duration_ms=ms,
            success=ok,
        )
    summary = store.get_tool_summary("search_leads")
    assert summary["total_calls"] == 5
    assert summary["success_rate"] == pytest.approx(0.8)
    # p50 of [10, 20, 30, 40, 100] is 30; p95 is between 40 and 100
    assert summary["p50_latency_ms"] == pytest.approx(30.0, abs=0.5)
    assert summary["p95_latency_ms"] > 40.0
    assert summary["p99_latency_ms"] >= summary["p95_latency_ms"]


# ---------------------------------------------------------------------------
# 3. get_top_tools_by_cost ranking
# ---------------------------------------------------------------------------

def test_get_top_tools_by_cost_ranks_descending(store):
    # tool_cheap: small token spend on haiku
    store.record_tool_call("a", "r", "tool_cheap", 100, 50, model="claude-haiku-4-5")
    # tool_mid: moderate on sonnet
    store.record_tool_call("a", "r", "tool_mid", 1000, 500, model="claude-sonnet-4-6")
    # tool_expensive: heavy spend on opus
    store.record_tool_call("a", "r", "tool_expensive", 5000, 2500, model="claude-opus-4-7")

    rows = store.get_top_tools_by_cost(limit=10)
    assert len(rows) == 3
    # Descending by cost
    assert rows[0]["tool_name"] == "tool_expensive"
    assert rows[1]["tool_name"] == "tool_mid"
    assert rows[2]["tool_name"] == "tool_cheap"
    assert rows[0]["estimated_cost_usd"] > rows[1]["estimated_cost_usd"]
    assert rows[1]["estimated_cost_usd"] > rows[2]["estimated_cost_usd"]


# ---------------------------------------------------------------------------
# 4. Pricing math matches the rate table
# ---------------------------------------------------------------------------

def test_pricing_math_uses_rate_table(store):
    in_tok, out_tok = 1000, 1000
    store.record_tool_call(
        "a", "r", "billed_tool",
        input_tokens=in_tok, output_tokens=out_tok,
        model="claude-opus-4-7", duration_ms=1.0, success=True,
    )
    rate = _PRICING["claude-opus-4-7"]
    expected = (in_tok / 1000.0) * rate["input"] + (out_tok / 1000.0) * rate["output"]
    summary = store.get_tool_summary("billed_tool")
    assert summary["estimated_cost_usd"] == pytest.approx(expected, abs=1e-6)


# ---------------------------------------------------------------------------
# 5. Admin route auth gate (rejects when admin guard raises)
# ---------------------------------------------------------------------------

def test_route_requires_admin():
    """Ensure the new /tools/* routes are guarded by require_admin."""
    pytest.importorskip("fastapi")
    from fastapi import FastAPI, HTTPException
    from fastapi.testclient import TestClient

    # Build a minimal app and load the router module directly.
    spec = importlib.util.spec_from_file_location(
        "_perennia_gov_routes",
        str(_BACKEND_DIR / "routes" / "agent_governance_metrics_routes.py"),
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]

    app = FastAPI()

    # Override deps to simulate non-admin user.
    def _user():
        return {"id": "u1"}

    def _admin_denied():
        raise HTTPException(status_code=403, detail="admin required")

    app.dependency_overrides[module.get_current_user] = _user
    app.dependency_overrides[module.require_admin] = _admin_denied
    app.include_router(module.router)

    client = TestClient(app)
    resp = client.get("/api/v1/agents/governance/tools/summary")
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 6. Admin route response shape
# ---------------------------------------------------------------------------

def test_route_response_shape_for_tools_summary():
    pytest.importorskip("fastapi")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    spec = importlib.util.spec_from_file_location(
        "_perennia_gov_routes_v2",
        str(_BACKEND_DIR / "routes" / "agent_governance_metrics_routes.py"),
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]

    # Replace the store factory so the route reads from our fresh store.
    fresh = GovernanceMetricsStore()
    fresh.record_tool_call("a", "r", "demo_tool", 100, 50,
                           model="claude-sonnet-4-6", duration_ms=12.0, success=True)
    module._store = lambda: fresh  # type: ignore[assignment]

    app = FastAPI()
    app.dependency_overrides[module.get_current_user] = lambda: {"id": "u1"}
    app.dependency_overrides[module.require_admin] = lambda: True
    app.include_router(module.router)

    client = TestClient(app)
    resp = client.get("/api/v1/agents/governance/tools/summary?limit=5")
    assert resp.status_code == 200
    body = resp.json()
    assert "count" in body and "tools" in body
    assert body["count"] == 1
    assert body["tools"][0]["tool_name"] == "demo_tool"
    assert "estimated_cost_usd" in body["tools"][0]
    assert "p95_latency_ms" in body["tools"][0]

    # Per-tool detail route
    resp2 = client.get("/api/v1/agents/governance/tools/demo_tool")
    assert resp2.status_code == 200
    detail = resp2.json()
    assert detail["tool_name"] == "demo_tool"
    assert detail["total_calls"] == 1
