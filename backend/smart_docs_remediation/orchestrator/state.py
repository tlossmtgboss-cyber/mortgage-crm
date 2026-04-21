"""Shared state schema for the Smart Docs remediation LangGraph.

A single mutable state object flows through every node. Agents read
what they need from `context` and append to `agent_outputs`,
`patches`, `issues`, and `telemetry`.

Design choices
--------------
- We use TypedDict (not Pydantic) because LangGraph's default reducer
  semantics work best with plain dicts.
- `agent_outputs` is an append-only dict keyed by agent id so replays
  are deterministic.
- Every mutation carries a timestamp and the producing agent id so
  the observer (M100) can reconstruct the run.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any, Literal, TypedDict

from operator import add


Tier = Literal["critical", "important", "consider", "meta"]
AgentStatus = Literal[
    "pending",
    "scheduled",
    "running",
    "waiting_human",
    "succeeded",
    "failed",
    "skipped",
    "rolled_back",
]
PatchStatus = Literal["generated", "merged", "reverted", "rejected"]


class AgentSpec(TypedDict, total=False):
    """Subset of the YAML definition we actually read at runtime."""
    id: str
    name: str
    tier: Tier
    finding_refs: list[int]
    mission: str
    inputs: list[str]
    outputs: list[str]
    depends_on: list[str]
    tools: list[str]
    model: str
    autonomy: Literal["auto", "review_required", "human_approval"]
    risk: Literal["low", "medium", "high"]


class AgentResult(TypedDict, total=False):
    agent_id: str
    status: AgentStatus
    started_at: str
    finished_at: str
    model: str
    # Natural-language reasoning produced by the agent
    summary: str
    # Structured outputs: paths to produced artifacts keyed by logical name
    artifacts: dict[str, str]
    # Patches the agent wants applied (path -> unified diff)
    patches: dict[str, str]
    # Tests the agent wrote (path -> source)
    tests: dict[str, str]
    # If the agent failed, why
    error: str | None
    # Token usage for cost tracking
    tokens_in: int
    tokens_out: int


class TelemetryEvent(TypedDict):
    ts: str
    agent_id: str
    kind: str  # "info" | "warn" | "error" | "progress"
    message: str
    meta: dict[str, Any]


class HumanApproval(TypedDict):
    agent_id: str
    requested_at: str
    decided_at: str | None
    decision: Literal["pending", "approved", "rejected"]
    reviewer: str | None
    notes: str


class RunState(TypedDict, total=False):
    """Top-level state passed through the graph."""

    # --- immutable run metadata ---
    run_id: str
    started_at: str
    codebase_root: str  # path to the Perennia monorepo checkout
    selected_findings: list[int]  # optional filter; empty = all
    dry_run: bool

    # --- agent registry ---
    agents: dict[str, AgentSpec]  # id -> spec
    execution_plan: list[list[str]]  # list of parallel groups

    # --- per-agent results ---
    agent_outputs: Annotated[dict[str, AgentResult], lambda a, b: {**a, **b}]

    # --- aggregated artifacts ---
    patches: Annotated[dict[str, PatchStatus], lambda a, b: {**a, **b}]
    open_issues: Annotated[list[str], add]  # surfaced problems

    # --- human-in-the-loop ---
    approvals: Annotated[list[HumanApproval], add]

    # --- telemetry ---
    telemetry: Annotated[list[TelemetryEvent], add]

    # --- final state ---
    status: Literal["planning", "executing", "awaiting_approval", "done", "aborted"]


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def fresh_run_state(
    run_id: str,
    codebase_root: str,
    selected_findings: list[int] | None = None,
    dry_run: bool = False,
) -> RunState:
    return RunState(
        run_id=run_id,
        started_at=utcnow_iso(),
        codebase_root=codebase_root,
        selected_findings=selected_findings or [],
        dry_run=dry_run,
        agents={},
        execution_plan=[],
        agent_outputs={},
        patches={},
        open_issues=[],
        approvals=[],
        telemetry=[],
        status="planning",
    )
