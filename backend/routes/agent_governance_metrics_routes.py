"""
Agent Governance Metrics — Read-Only Dashboard API (Wave 3)
===========================================================

Exposes the in-process ``governance_metrics`` store (Wave 3, D3 audit
remediation #2) as a small read-only HTTP API for the per-agent governance
dashboard.

Storage caveat: the underlying store is **process-local** (see
``agents/orchestration/governance_metrics.py``). In a multi-worker deployment
each worker returns its own slice; a Wave 4 candidate is to externalize the
store (Redis Streams / Postgres).

All endpoints require an authenticated administrator (``require_admin``).
The existing legacy router lives at prefix ``/api/v1/agents``; this router
deliberately scopes itself one level deeper at ``/api/v1/agents/governance``
to avoid path collisions with that file's ``/governance/settings`` and
``/governance/dashboard`` endpoints (FastAPI routes are matched in
registration order, and neither of those collides with the routes added
here: ``/summary``, ``/agents/{agent_id}``, ``/compliance/recent``,
``/hallucinations/recent``, ``/budgets``).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query

logger = logging.getLogger(__name__)

# Lazy/late imports for resilience: if the FastAPI app can't satisfy these
# at import time the router still loads, but every endpoint will 503.
try:
    from auth.dependencies import get_current_user
except Exception as _exc:  # pragma: no cover - defensive  # noqa: BLE001
    logger.exception("unhandled exception")
    def get_current_user():
        raise HTTPException(status_code=503, detail="auth unavailable")

try:
    from middleware.admin_guard import require_admin
except Exception as _exc:  # pragma: no cover - defensive  # noqa: BLE001
    logger.exception("unhandled exception")
    def require_admin():
        raise HTTPException(status_code=503, detail="admin guard unavailable")

router = APIRouter(
    prefix="/api/v1/agents/governance",
    tags=["agent-governance"],
)


def _store():
    """Resolve the in-process metrics store. Late import keeps the router
    importable even if the agents package is being constructed mid-startup.
    """
    from agents.orchestration.governance_metrics import governance_metrics
    return governance_metrics


def _budgets():
    from agents.orchestration.token_budget import token_budget_manager
    return token_budget_manager


# ---------------------------------------------------------------------------
# Fleet-wide summary
# ---------------------------------------------------------------------------

@router.get("/summary")
async def get_governance_fleet_summary(
    top_n: int = Query(5, ge=1, le=50),
    _user: Any = Depends(get_current_user),
    _admin: Any = Depends(require_admin),
) -> Dict[str, Any]:
    """Fleet-wide per-role roll-up plus top-N hot spots."""
    try:
        return _store().get_fleet_summary(top_n=top_n)
    except Exception as exc:  # noqa: BLE001
        logger.error("governance fleet summary failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


# ---------------------------------------------------------------------------
# Per-agent summary
# ---------------------------------------------------------------------------

@router.get("/agents/{agent_id}")
async def get_governance_agent_summary(
    agent_id: str,
    last_n: int = Query(20, ge=0, le=200),
    _user: Any = Depends(get_current_user),
    _admin: Any = Depends(require_admin),
) -> Dict[str, Any]:
    """Aggregate counters + last-N events for one agent."""
    try:
        return _store().get_per_agent_summary(agent_id, last_n=last_n)
    except Exception as exc:  # noqa: BLE001
        logger.error("governance agent summary failed (%s): %s", agent_id, exc)
        raise HTTPException(status_code=500, detail="Internal server error")


# ---------------------------------------------------------------------------
# Recent compliance events
# ---------------------------------------------------------------------------

@router.get("/compliance/recent")
async def get_recent_compliance_events(
    limit: int = Query(50, ge=1, le=1000),
    _user: Any = Depends(get_current_user),
    _admin: Any = Depends(require_admin),
) -> Dict[str, Any]:
    """Most recent compliance events, newest first."""
    try:
        events = _store().recent_compliance(limit=limit)
        return {"count": len(events), "events": events}
    except Exception as exc:  # noqa: BLE001
        logger.error("governance recent compliance failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


# ---------------------------------------------------------------------------
# Recent hallucination events
# ---------------------------------------------------------------------------

@router.get("/hallucinations/recent")
async def get_recent_hallucination_events(
    limit: int = Query(50, ge=1, le=1000),
    _user: Any = Depends(get_current_user),
    _admin: Any = Depends(require_admin),
) -> Dict[str, Any]:
    """Most recent hallucination grounding checks, newest first."""
    try:
        events = _store().recent_hallucinations(limit=limit)
        return {"count": len(events), "events": events}
    except Exception as exc:  # noqa: BLE001
        logger.error("governance recent hallucinations failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


# ---------------------------------------------------------------------------
# Per-agent token budget utilization (live)
# ---------------------------------------------------------------------------

@router.get("/budgets")
async def get_budget_utilization(
    _user: Any = Depends(get_current_user),
    _admin: Any = Depends(require_admin),
) -> Dict[str, Any]:
    """
    Per-agent token budget utilization for today.

    Sources the list of known agents from the metrics store and the live
    counters from the TokenBudgetManager singleton.
    """
    try:
        mgr = _budgets()
        store = _store()
        # Collect every agent_id we've seen recently.
        fleet = store.get_fleet_summary(top_n=1)
        agent_ids: List[str] = [a["agent_id"] for a in fleet.get("per_agent", [])]
        out: List[Dict[str, Any]] = []
        for aid in agent_ids:
            snap = mgr.get_usage(aid)
            snap["agent_id"] = aid
            out.append(snap)
        return {
            "generated_at": fleet.get("generated_at"),
            "agent_count": len(out),
            "budgets": out,
        }
    except Exception as exc:  # noqa: BLE001
        logger.error("governance budgets endpoint failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


__all__ = ["router"]
