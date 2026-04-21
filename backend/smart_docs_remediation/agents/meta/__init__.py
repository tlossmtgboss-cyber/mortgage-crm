"""Meta-tier agents — orchestration, safety, observability.

These agents do not call the Anthropic API on a hot path. They're
plain Python wrappers that conform to the BaseAgent interface so the
rest of the system treats them uniformly.
"""
from __future__ import annotations

import json
import logging
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

from agents.base import AgentEnvelope, BaseAgent
from orchestrator.state import AgentResult, RunState, utcnow_iso

log = logging.getLogger(__name__)


# ============================================================================
# M91 — Coordinator
# ============================================================================


class Coordinator(BaseAgent):
    """Top-level orchestration entry point.

    The coordinator does NOT call the model. It simply publishes a
    structured run plan to disk so the LangGraph runner can execute it.
    Keeping this logic outside the model ensures runs are deterministic
    and replayable.
    """

    def run(self, state: RunState) -> AgentResult:
        started = utcnow_iso()

        plan_path = Path(f"state/run_{state['run_id']}.json")
        plan_path.parent.mkdir(exist_ok=True)
        plan_path.write_text(json.dumps({
            "run_id": state["run_id"],
            "started_at": state["started_at"],
            "agent_count": len(state.get("agents", {})),
            "execution_plan": state.get("execution_plan", []),
            "dry_run": state.get("dry_run", False),
        }, indent=2))

        return {
            "agent_id": self.spec["id"],
            "status": "succeeded",
            "started_at": started,
            "finished_at": utcnow_iso(),
            "model": "local",
            "summary": f"Coordinator wrote plan to {plan_path}",
            "artifacts": {"run_plan": str(plan_path)},
            "patches": {},
            "tests": {},
            "error": None,
            "tokens_in": 0,
            "tokens_out": 0,
        }

    def build_prompt(self, state: RunState) -> list[dict[str, Any]]:
        return []  # unused


# ============================================================================
# M92 — Dependency Resolver
# ============================================================================


class DependencyResolver(BaseAgent):
    """Topologically sorts agents into parallel groups.

    Writes the execution plan back into state. Detects cycles early so
    they fail loud rather than deadlock the graph.
    """

    def run(self, state: RunState) -> AgentResult:
        started = utcnow_iso()
        agents = state.get("agents", {})

        # Build adjacency & indegree
        indeg: dict[str, int] = defaultdict(int)
        children: dict[str, list[str]] = defaultdict(list)
        for aid, spec in agents.items():
            for dep in spec.get("depends_on", []):
                if dep not in agents:
                    log.warning("agent %s depends on unknown agent %s", aid, dep)
                    continue
                children[dep].append(aid)
                indeg[aid] += 1

        # Kahn's algorithm with parallel-group output
        ready = deque(a for a in agents if indeg[a] == 0)
        plan: list[list[str]] = []
        visited: set[str] = set()

        while ready:
            group = sorted(ready)
            plan.append(group)
            ready.clear()
            for aid in group:
                visited.add(aid)
                for child in children.get(aid, []):
                    indeg[child] -= 1
                    if indeg[child] == 0:
                        ready.append(child)

        if len(visited) != len(agents):
            missing = set(agents) - visited
            raise RuntimeError(f"Dependency cycle involving: {missing}")

        # Mutate state in place via our side-channel
        state["execution_plan"] = plan

        plan_summary = (
            f"{len(plan)} parallel groups, "
            f"max parallelism = {max(len(g) for g in plan) if plan else 0}"
        )
        log.info("dependency plan: %s", plan_summary)

        return {
            "agent_id": self.spec["id"],
            "status": "succeeded",
            "started_at": started,
            "finished_at": utcnow_iso(),
            "model": "local",
            "summary": plan_summary,
            "artifacts": {"plan_groups": str(len(plan))},
            "patches": {},
            "tests": {},
            "error": None,
            "tokens_in": 0,
            "tokens_out": 0,
        }

    def build_prompt(self, state: RunState) -> list[dict[str, Any]]:
        return []


# ============================================================================
# M93 — Conflict Detector
# ============================================================================


class ConflictDetector(BaseAgent):
    """Flags agents whose patches touch overlapping files."""

    def run(self, state: RunState) -> AgentResult:
        started = utcnow_iso()
        touched: dict[str, list[str]] = defaultdict(list)
        for aid, result in state.get("agent_outputs", {}).items():
            for path in result.get("patches", {}):
                touched[path].append(aid)

        conflicts = {path: owners for path, owners in touched.items() if len(owners) > 1}
        summary = (
            f"{len(conflicts)} file(s) touched by multiple agents"
            if conflicts else "no conflicts"
        )

        return {
            "agent_id": self.spec["id"],
            "status": "succeeded",
            "started_at": started,
            "finished_at": utcnow_iso(),
            "model": "local",
            "summary": summary,
            "artifacts": {"conflicts": json.dumps(conflicts)},
            "patches": {},
            "tests": {},
            "error": None,
            "tokens_in": 0,
            "tokens_out": 0,
        }

    def build_prompt(self, state: RunState) -> list[dict[str, Any]]:
        return []


# ============================================================================
# M99 — Human Approver
# ============================================================================


class HumanApprover(BaseAgent):
    """Surfaces agents awaiting human approval.

    In production this integrates with a Slack bot or the Perennia admin
    dashboard. Here it emits a structured approval request and blocks.
    """

    def run(self, state: RunState) -> AgentResult:
        started = utcnow_iso()
        pending = [
            (aid, r) for aid, r in state.get("agent_outputs", {}).items()
            if r.get("status") == "waiting_human"
        ]

        approvals_path = Path("state/approvals_pending.json")
        approvals_path.parent.mkdir(exist_ok=True)
        approvals_path.write_text(json.dumps([
            {
                "agent_id": aid,
                "summary": r.get("summary", ""),
                "patches": list(r.get("patches", {}).keys()),
                "risk": state.get("agents", {}).get(aid, {}).get("risk"),
            }
            for aid, r in pending
        ], indent=2))

        return {
            "agent_id": self.spec["id"],
            "status": "succeeded",
            "started_at": started,
            "finished_at": utcnow_iso(),
            "model": "local",
            "summary": f"{len(pending)} agent(s) awaiting human review",
            "artifacts": {"pending_approvals": str(approvals_path)},
            "patches": {},
            "tests": {},
            "error": None,
            "tokens_in": 0,
            "tokens_out": 0,
        }

    def build_prompt(self, state: RunState) -> list[dict[str, Any]]:
        return []


# ============================================================================
# M100 — Observer
# ============================================================================


class Observer(BaseAgent):
    """Central telemetry — writes a final run report."""

    def run(self, state: RunState) -> AgentResult:
        started = utcnow_iso()

        outputs = state.get("agent_outputs", {})
        by_status: dict[str, int] = defaultdict(int)
        total_in = total_out = 0
        for r in outputs.values():
            by_status[r.get("status", "unknown")] += 1
            total_in += r.get("tokens_in", 0) or 0
            total_out += r.get("tokens_out", 0) or 0

        report_path = Path(f"state/run_{state['run_id']}_report.json")
        report_path.parent.mkdir(exist_ok=True)
        report_path.write_text(json.dumps({
            "run_id": state["run_id"],
            "started_at": state.get("started_at"),
            "finished_at": utcnow_iso(),
            "counts_by_status": dict(by_status),
            "total_tokens_in": total_in,
            "total_tokens_out": total_out,
            "patches_generated": sum(
                len(r.get("patches", {})) for r in outputs.values()
            ),
            "tests_generated": sum(
                len(r.get("tests", {})) for r in outputs.values()
            ),
            "findings_addressed": sorted({
                fid
                for aid in outputs
                for fid in state.get("agents", {}).get(aid, {}).get("finding_refs", [])
            }),
        }, indent=2))

        return {
            "agent_id": self.spec["id"],
            "status": "succeeded",
            "started_at": started,
            "finished_at": utcnow_iso(),
            "model": "local",
            "summary": (
                f"{sum(by_status.values())} agents finished; "
                f"{by_status.get('succeeded', 0)} succeeded, "
                f"{by_status.get('waiting_human', 0)} awaiting approval, "
                f"{by_status.get('failed', 0)} failed"
            ),
            "artifacts": {"run_report": str(report_path)},
            "patches": {},
            "tests": {},
            "error": None,
            "tokens_in": 0,
            "tokens_out": 0,
        }

    def build_prompt(self, state: RunState) -> list[dict[str, Any]]:
        return []


__all__ = [
    "Coordinator",
    "DependencyResolver",
    "ConflictDetector",
    "HumanApprover",
    "Observer",
]
