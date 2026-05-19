"""
Integration tests for the agent governance metrics dashboard router.

Mounts the router on an isolated FastAPI app (bypassing main.py) and uses
TestClient with admin/non-admin dependency overrides to exercise the five
GET endpoints exposed at /api/v1/agents/governance/*.

The store is the in-process singleton from
backend/agents/orchestration/governance_metrics.py, loaded via the same
importlib pattern as test_governance_metrics_store.py.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


pytestmark = pytest.mark.integration

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.testclient import TestClient
except Exception:  # pragma: no cover - fastapi missing
    pytest.skip("fastapi not installed", allow_module_level=True)


_BACKEND_DIR = Path(__file__).resolve().parents[2]


def _load(rel: str, mod: str):
    target = _BACKEND_DIR / rel
    if not target.exists():
        pytest.skip(f"{rel} missing")
    spec = importlib.util.spec_from_file_location(mod, str(target))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


# Load the store module (and its singleton) via the importlib pattern so the
# router's `from agents.orchestration.governance_metrics import governance_metrics`
# lookup hits the same instance.
_gm = _load(
    "agents/orchestration/governance_metrics.py",
    "agents.orchestration.governance_metrics",
)

# Stub the token_budget module so the /budgets endpoint can import it without
# pulling in the full agents package.
import types as _types
_tb = _types.ModuleType("agents.orchestration.token_budget")


class _StubBudget:
    def get_usage(self, agent_id):
        return {"tokens_used": 0, "tokens_remaining": 100000, "budget": 100000}


_tb.token_budget_manager = _StubBudget()
sys.modules["agents.orchestration.token_budget"] = _tb

# Reset the store so tests start from a clean slate.
_gm.governance_metrics.reset()
# Seed a couple of events so endpoints have data to return.
_gm.governance_metrics.record_compliance_event(
    "agent_alpha", "lead_nurturer", 1, [{"rule": "TRID"}], False
)
_gm.governance_metrics.record_hallucination_event(
    "agent_alpha", "lead_nurturer", 0.82, ["7%"]
)
_gm.governance_metrics.record_token_usage("agent_alpha", "lead_nurturer", 100, 50)


# Now load the router module. Its lazy imports for auth/admin guard run at
# import time and define no-op fallbacks if the real deps aren't reachable —
# that's fine because we'll override them via app.dependency_overrides.
_routes = _load(
    "routes/agent_governance_metrics_routes.py",
    "_perennia_agent_gov_metrics_routes",
)


def _make_app(admin_ok: bool = True) -> FastAPI:
    app = FastAPI()
    app.include_router(_routes.router)

    # Override dependencies so we control auth/admin in tests.
    def _user_dep():
        return {"id": 1, "email": "admin@perenniaai.com", "role": "admin"}

    def _admin_dep():
        if not admin_ok:
            raise HTTPException(status_code=403, detail="admin required")
        return True

    # The router uses the in-module symbols `get_current_user` and
    # `require_admin` directly via Depends().
    app.dependency_overrides[_routes.get_current_user] = _user_dep
    app.dependency_overrides[_routes.require_admin] = _admin_dep
    return app


# ---------------------------------------------------------------------------
# Test 1: GET /summary returns fleet roll-up
# ---------------------------------------------------------------------------

def test_summary_endpoint_returns_fleet_data():
    client = TestClient(_make_app(admin_ok=True))
    r = client.get("/api/v1/agents/governance/summary")
    assert r.status_code == 200
    data = r.json()
    assert "agent_count" in data
    assert data["agent_count"] >= 1


# ---------------------------------------------------------------------------
# Test 2: GET /agents/{agent_id} returns per-agent summary
# ---------------------------------------------------------------------------

def test_agent_summary_endpoint_returns_keyed_data():
    client = TestClient(_make_app(admin_ok=True))
    r = client.get("/api/v1/agents/governance/agents/agent_alpha")
    assert r.status_code == 200
    data = r.json()
    assert data["agent_id"] == "agent_alpha"


# ---------------------------------------------------------------------------
# Test 3: GET /compliance/recent returns paginated list with count+events
# ---------------------------------------------------------------------------

def test_compliance_recent_endpoint_shape():
    client = TestClient(_make_app(admin_ok=True))
    r = client.get("/api/v1/agents/governance/compliance/recent?limit=10")
    assert r.status_code == 200
    payload = r.json()
    assert "count" in payload and "events" in payload
    assert payload["count"] == len(payload["events"])


# ---------------------------------------------------------------------------
# Test 4: GET /hallucinations/recent returns the right shape
# ---------------------------------------------------------------------------

def test_hallucinations_recent_endpoint_shape():
    client = TestClient(_make_app(admin_ok=True))
    r = client.get("/api/v1/agents/governance/hallucinations/recent?limit=5")
    assert r.status_code == 200
    payload = r.json()
    assert "count" in payload and "events" in payload


# ---------------------------------------------------------------------------
# Test 5: GET /budgets returns per-agent budget snapshot
# ---------------------------------------------------------------------------

def test_budgets_endpoint_returns_per_agent_snapshots():
    client = TestClient(_make_app(admin_ok=True))
    r = client.get("/api/v1/agents/governance/budgets")
    assert r.status_code == 200
    payload = r.json()
    assert "budgets" in payload
    assert "agent_count" in payload


# ---------------------------------------------------------------------------
# Test 6: Non-admin gets 403 from the admin guard
# ---------------------------------------------------------------------------

def test_non_admin_blocked_with_403():
    client = TestClient(_make_app(admin_ok=False))
    r = client.get("/api/v1/agents/governance/summary")
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Test 7: limit query param respects upper/lower bounds (FastAPI validation)
# ---------------------------------------------------------------------------

def test_compliance_recent_rejects_oversized_limit():
    client = TestClient(_make_app(admin_ok=True))
    # Query ge=1 le=1000 — 2000 should 422 from FastAPI validation
    r = client.get("/api/v1/agents/governance/compliance/recent?limit=2000")
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Test 8: Empty store returns empty events list (after reset)
# ---------------------------------------------------------------------------

def test_empty_store_returns_zero_events():
    _gm.governance_metrics.reset()
    client = TestClient(_make_app(admin_ok=True))
    r = client.get("/api/v1/agents/governance/compliance/recent?limit=50")
    assert r.status_code == 200
    payload = r.json()
    assert payload["count"] == 0
    assert payload["events"] == []
