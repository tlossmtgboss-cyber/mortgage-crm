"""LangGraph orchestrator.

The graph topology:

    plan ──► dispatch ──► [parallel group execution] ──► gate ──►
            │                                            │
            │                                            ▼
            │                                      more_groups?
            │                                            │
            └──────────────── no ───────── yes ──────────┘
                                            │
                                            ▼
                                         finalize

Each parallel group is a list of agent ids produced by M92's topological
sort. We execute them concurrently inside a ThreadPoolExecutor — the
agents are I/O bound (Anthropic API) so threads are sufficient; no need
for asyncio for this first pass.

The state object is the RunState TypedDict. Reducers for annotated
keys merge dict updates and append list updates.
"""
from __future__ import annotations

import logging
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from langgraph.graph import END, StateGraph

from agents.registry import AgentRegistry
from orchestrator.state import (
    AgentResult,
    RunState,
    TelemetryEvent,
    fresh_run_state,
    utcnow_iso,
)

log = logging.getLogger(__name__)


# ----------------------------------------------------------------------------
# Graph nodes
# ----------------------------------------------------------------------------


def plan_node(state: RunState, *, registry: AgentRegistry) -> dict[str, Any]:
    """Populate `agents` and `execution_plan` from the registry."""
    specs = registry.specs_for_findings(state.get("selected_findings", []))
    agent_map = {s["id"]: s for s in specs}

    # Build execution plan via M92 directly — avoids chicken-and-egg problem
    state["agents"] = agent_map  # type: ignore[typeddict-item]
    resolver = registry.build("M92")
    result = resolver.run(state)
    # resolver mutated state["execution_plan"] in place

    event: TelemetryEvent = {
        "ts": utcnow_iso(),
        "agent_id": "plan",
        "kind": "info",
        "message": f"scheduled {len(agent_map)} agents across {len(state['execution_plan'])} groups",
        "meta": {
            "parallelism": max((len(g) for g in state["execution_plan"]), default=0),
        },
    }

    return {
        "agents": agent_map,
        "execution_plan": state["execution_plan"],
        "agent_outputs": {"M92": result},
        "status": "executing",
        "telemetry": [event],
    }


def _group_index(state: RunState) -> int:
    """How many groups have we already completed?"""
    return len(
        [
            g for g in state.get("execution_plan", [])
            if all(aid in state.get("agent_outputs", {}) for aid in g)
        ]
    )


def dispatch_node(
    state: RunState,
    *,
    registry: AgentRegistry,
    max_workers: int = 8,
) -> dict[str, Any]:
    """Execute the next parallel group of agents."""
    plan = state.get("execution_plan", [])
    idx = _group_index(state)
    if idx >= len(plan):
        return {}

    group = plan[idx]
    # Skip already-completed agents within this group
    todo = [aid for aid in group if aid not in state.get("agent_outputs", {})]
    if not todo:
        return {}

    log.info("dispatch group %d/%d (%d agents)", idx + 1, len(plan), len(todo))
    results: dict[str, AgentResult] = {}
    events: list[TelemetryEvent] = []

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(registry.build(aid).run, state): aid for aid in todo}
        for fut in as_completed(futures):
            aid = futures[fut]
            try:
                results[aid] = fut.result()
                events.append({
                    "ts": utcnow_iso(),
                    "agent_id": aid,
                    "kind": "progress",
                    "message": f"agent {aid} finished with status {results[aid].get('status')}",
                    "meta": {"tokens_out": results[aid].get("tokens_out", 0)},
                })
            except Exception as exc:  # noqa: BLE001
                log.exception("agent %s crashed", aid)
                results[aid] = {
                    "agent_id": aid,
                    "status": "failed",
                    "started_at": utcnow_iso(),
                    "finished_at": utcnow_iso(),
                    "model": "unknown",
                    "summary": "",
                    "artifacts": {},
                    "patches": {},
                    "tests": {},
                    "error": str(exc),
                    "tokens_in": 0,
                    "tokens_out": 0,
                }
                events.append({
                    "ts": utcnow_iso(),
                    "agent_id": aid,
                    "kind": "error",
                    "message": f"agent {aid} crashed: {exc}",
                    "meta": {},
                })

    return {"agent_outputs": results, "telemetry": events}


def gate_node(state: RunState, *, registry: AgentRegistry) -> dict[str, Any]:
    """Run M93 (conflict detector) + M99 (human approver) after each group."""
    detector = registry.build("M93")
    approver = registry.build("M99")

    m93 = detector.run(state)
    m99 = approver.run(state)

    outputs = {"M93": m93, "M99": m99}
    events: list[TelemetryEvent] = [
        {
            "ts": utcnow_iso(),
            "agent_id": "M93",
            "kind": "info",
            "message": m93.get("summary", ""),
            "meta": {},
        },
        {
            "ts": utcnow_iso(),
            "agent_id": "M99",
            "kind": "info",
            "message": m99.get("summary", ""),
            "meta": {},
        },
    ]
    return {"agent_outputs": outputs, "telemetry": events}


def finalize_node(state: RunState, *, registry: AgentRegistry) -> dict[str, Any]:
    observer = registry.build("M100")
    result = observer.run(state)
    return {
        "agent_outputs": {"M100": result},
        "status": "done",
        "telemetry": [{
            "ts": utcnow_iso(),
            "agent_id": "M100",
            "kind": "info",
            "message": result.get("summary", ""),
            "meta": {},
        }],
    }


# ----------------------------------------------------------------------------
# Graph construction
# ----------------------------------------------------------------------------


def _has_more_groups(state: RunState) -> str:
    idx = _group_index(state)
    plan = state.get("execution_plan", [])
    return "dispatch" if idx < len(plan) else "finalize"


def build_graph(registry: AgentRegistry, max_workers: int = 8):
    g = StateGraph(RunState)

    g.add_node("plan", lambda s: plan_node(s, registry=registry))
    g.add_node("dispatch", lambda s: dispatch_node(s, registry=registry, max_workers=max_workers))
    g.add_node("gate", lambda s: gate_node(s, registry=registry))
    g.add_node("finalize", lambda s: finalize_node(s, registry=registry))

    g.set_entry_point("plan")
    g.add_edge("plan", "dispatch")
    g.add_edge("dispatch", "gate")
    g.add_conditional_edges("gate", _has_more_groups, {
        "dispatch": "dispatch",
        "finalize": "finalize",
    })
    g.add_edge("finalize", END)

    return g.compile()


# ----------------------------------------------------------------------------
# Convenience runner
# ----------------------------------------------------------------------------


def run_remediation(
    codebase_root: str | Path,
    *,
    selected_findings: list[int] | None = None,
    dry_run: bool = True,
    max_workers: int = 8,
    registry_path: str | Path = "config/agents.yaml",
) -> RunState:
    registry = AgentRegistry(Path(registry_path))
    graph = build_graph(registry, max_workers=max_workers)
    initial = fresh_run_state(
        run_id=str(uuid.uuid4())[:8],
        codebase_root=str(codebase_root),
        selected_findings=selected_findings,
        dry_run=dry_run,
    )
    final: RunState = graph.invoke(initial)  # type: ignore[assignment]
    return final
