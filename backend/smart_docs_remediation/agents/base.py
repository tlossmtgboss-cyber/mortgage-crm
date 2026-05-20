"""Base agent infrastructure.

Every one of the 100 agents inherits from :class:`BaseAgent`. The base
class handles:

* Anthropic API calls with the model chosen in ``agents.yaml``.
* Tool-permission enforcement (an agent declared with ``tools: [read]``
  cannot issue a write call).
* Structured output extraction — agents must emit a single JSON block
  that conforms to :class:`AgentEnvelope`.
* Retry with exponential backoff on transient errors.
* Token/cost accounting fed to the observer.

We deliberately keep the base class thin. Specialist subclasses add
their own prompt scaffolding and post-processing.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import anthropic

from orchestrator.state import AgentResult, AgentSpec, RunState, utcnow_iso

log = logging.getLogger(__name__)

# ----------------------------------------------------------------------------
# Tool registry
# ----------------------------------------------------------------------------
# Agents declare which tools they need in agents.yaml. At runtime we map
# each tool name to a callable. This keeps a single chokepoint for
# permission enforcement.


TOOL_CATALOG: dict[str, str] = {
    "read": "Read a file or directory from the codebase.",
    "grep": "Regex search across the codebase.",
    "ast_walk": "Walk the Python AST of a file.",
    "ts_ast": "Walk the TypeScript AST of a file.",
    "static_analysis": "Run type-checkers / linters.",
    "patch": "Produce a unified diff for a file.",
    "write": "Create a new file at a given path.",
    "write_test": "Create a test file.",
    "migrate": "Produce an Alembic migration.",
    "celery": "Register a Celery periodic task.",
    "sql_read": "Read-only SQL query against the staging DB.",
    "sql_explain": "EXPLAIN a SQL statement.",
    "git": "Git operations.",
    "github": "GitHub API (PR create, comment).",
    "test": "Run the test suite.",
    "deploy": "Trigger a deploy (blocked unless dry_run=false).",
    "datadog": "Emit metrics / create dashboards.",
    "log_query": "Query structured access logs.",
    "notify": "Notify a human reviewer.",
    "ci": "Create/update CI workflow files.",
    "all": "Meta agents only — unrestricted.",
}


# ----------------------------------------------------------------------------
# Envelope schema — what agents return
# ----------------------------------------------------------------------------


@dataclass
class AgentEnvelope:
    """Structured output every agent must produce.

    Agents are prompted to return a single JSON code block matching this
    schema. We parse it here and reject anything else so the pipeline
    stays deterministic.
    """

    summary: str
    artifacts: dict[str, str] = field(default_factory=dict)
    patches: dict[str, str] = field(default_factory=dict)
    tests: dict[str, str] = field(default_factory=dict)
    open_questions: list[str] = field(default_factory=list)
    human_approval_needed: bool = False
    approval_reason: str = ""


_JSON_BLOCK = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)


def parse_envelope(raw: str) -> AgentEnvelope:
    match = _JSON_BLOCK.search(raw)
    if not match:
        # Accept a bare JSON object too, for robustness.
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"Agent output did not contain a JSON envelope:\n{raw[:400]}"
            ) from e
    else:
        data = json.loads(match.group(1))

    return AgentEnvelope(
        summary=data.get("summary", "").strip(),
        artifacts=data.get("artifacts", {}) or {},
        patches=data.get("patches", {}) or {},
        tests=data.get("tests", {}) or {},
        open_questions=data.get("open_questions", []) or [],
        human_approval_needed=bool(data.get("human_approval_needed", False)),
        approval_reason=data.get("approval_reason", "") or "",
    )


# ----------------------------------------------------------------------------
# Base agent
# ----------------------------------------------------------------------------


class BaseAgent(ABC):
    """Inherit from this to build a remediation agent.

    Subclasses override :meth:`build_prompt` and optionally
    :meth:`postprocess`. The base class owns the API call, retries,
    and result shaping.
    """

    MAX_TOKENS = 4096
    MAX_RETRIES = 3
    BACKOFF_SECONDS = 2.0

    # Subclasses may raise this to true for findings where Opus is worth it.
    prefer_opus: bool = False

    def __init__(self, spec: AgentSpec, client: anthropic.Anthropic | None = None):
        self.spec = spec
        self.client = client or anthropic.Anthropic(
            api_key=os.environ.get("ANTHROPIC_API_KEY", "")
        )

    # ------------------------------------------------------------------ API

    def run(self, state: RunState) -> AgentResult:
        started = utcnow_iso()
        log.info("agent.start id=%s name=%s", self.spec["id"], self.spec["name"])

        try:
            prompt = self.build_prompt(state)
        except Exception as e:  # noqa: BLE001
            return self._failed(started, f"prompt build failed: {e}")

        try:
            raw, usage = self._call_model(prompt)
        except Exception as e:  # noqa: BLE001
            return self._failed(started, f"model call failed: {e}")

        try:
            env = parse_envelope(raw)
        except ValueError as e:
            return self._failed(started, str(e), tokens_in=usage[0], tokens_out=usage[1])

        # Let subclasses clean up / validate
        env = self.postprocess(env, state)

        finished = utcnow_iso()
        result: AgentResult = {
            "agent_id": self.spec["id"],
            "status": "succeeded" if not env.human_approval_needed else "waiting_human",
            "started_at": started,
            "finished_at": finished,
            "model": self.spec.get("model", "claude-sonnet-4-5"),
            "summary": env.summary,
            "artifacts": env.artifacts,
            "patches": env.patches,
            "tests": env.tests,
            "error": None,
            "tokens_in": usage[0],
            "tokens_out": usage[1],
        }
        log.info(
            "agent.done id=%s status=%s tokens_in=%d tokens_out=%d",
            self.spec["id"], result["status"], usage[0], usage[1],
        )
        return result

    # --------------------------------------------------------- overrides

    @abstractmethod
    def build_prompt(self, state: RunState) -> list[dict[str, Any]]:
        """Return the messages array for the Anthropic API call.

        Must include a system directive and a user message instructing
        the model to return an :class:`AgentEnvelope` JSON block.
        """

    def postprocess(self, env: AgentEnvelope, state: RunState) -> AgentEnvelope:
        """Hook for subclass-specific validation. Default: pass through."""
        return env

    # ------------------------------------------------------------- helpers

    def _call_model(self, messages: list[dict[str, Any]]) -> tuple[str, tuple[int, int]]:
        """Issue an Anthropic API request with retries."""
        model = self.spec.get("model", "claude-sonnet-4-5")
        # System message pulled to top-level; Anthropic API expects it separately.
        system_parts = [m["content"] for m in messages if m["role"] == "system"]
        turns = [m for m in messages if m["role"] != "system"]
        system = "\n\n".join(system_parts)

        last_err: Exception | None = None
        for attempt in range(self.MAX_RETRIES):
            try:
                resp = self.client.messages.create(
                    model=model,
                    max_tokens=self.MAX_TOKENS,
                    system=system,
                    messages=turns,
                )
                text = "".join(
                    block.text for block in resp.content if block.type == "text"
                )
                return text, (resp.usage.input_tokens, resp.usage.output_tokens)
            except anthropic.APIStatusError as e:
                last_err = e
                if e.status_code in (429, 500, 502, 503, 529):
                    time.sleep(self.BACKOFF_SECONDS * (2 ** attempt))
                    continue
                raise
            except Exception as e:  # noqa: BLE001
                last_err = e
                time.sleep(self.BACKOFF_SECONDS * (2 ** attempt))
        assert last_err is not None
        raise last_err

    def _failed(self, started: str, error: str, tokens_in: int = 0, tokens_out: int = 0) -> AgentResult:
        log.error("agent.failed id=%s error=%s", self.spec["id"], error)
        return {
            "agent_id": self.spec["id"],
            "status": "failed",
            "started_at": started,
            "finished_at": utcnow_iso(),
            "model": self.spec.get("model", "claude-sonnet-4-5"),
            "summary": "",
            "artifacts": {},
            "patches": {},
            "tests": {},
            "error": error,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
        }


# ----------------------------------------------------------------------------
# Generic agent — used when no specialist subclass is registered
# ----------------------------------------------------------------------------


class GenericAgent(BaseAgent):
    """Fallback agent driven entirely by its YAML spec.

    This single class can run any agent whose mission is expressible as
    "read these inputs, think about the problem, produce these outputs".
    Specialist subclasses in agents/critical/ etc. can still override
    for finer control.
    """

    SYSTEM = """\
You are a specialist remediation agent embedded in the Perennia AI
Smart Docs remediation pipeline. You operate as part of a 100-agent
swarm. Your scope is strictly your mission. You do not comment on,
critique, or duplicate work owned by other agents.

Your output MUST be a single fenced JSON block matching this schema:

```json
{
  "summary": "One paragraph describing what you did and why.",
  "artifacts": { "<logical_name>": "<path_or_content>" },
  "patches":   { "<file_path>":   "<unified_diff>" },
  "tests":     { "<file_path>":   "<test_source>" },
  "open_questions": ["Questions the operator should resolve"],
  "human_approval_needed": false,
  "approval_reason": ""
}
```

Rules:
- Produce only the JSON block. No surrounding prose.
- If your mission is analysis-only, return artifacts; patches and tests stay empty.
- If your mission touches security, schema, or compliance, set
  human_approval_needed=true and explain in approval_reason.
- Prefer minimal, surgical patches. Unified diff format only.
- Every produced test must be runnable without network access.
"""

    def build_prompt(self, state: RunState) -> list[dict[str, Any]]:
        s = self.spec
        user = f"""\
# Mission (agent {s['id']} — {s['name']})

{s['mission']}

# Findings addressed

{", ".join(f"#{n}" for n in s.get('finding_refs', [])) or "(meta agent)"}

# Authorized tools

{", ".join(s.get('tools', []))}

# Inputs to consult

{chr(10).join(f"- {p}" for p in s.get('inputs', []))}

# Expected outputs

{chr(10).join(f"- {p}" for p in s.get('outputs', []))}

# Context from upstream agents

{self._render_upstream(state)}

# Risk classification

tier={s.get('tier')}, risk={s.get('risk')}, autonomy={s.get('autonomy')}

Produce the envelope now.
"""
        return [
            {"role": "system", "content": self.SYSTEM},
            {"role": "user", "content": user},
        ]

    def _render_upstream(self, state: RunState) -> str:
        deps = self.spec.get("depends_on", [])
        if not deps:
            return "(no upstream dependencies)"
        lines = []
        for dep_id in deps:
            dep = state.get("agent_outputs", {}).get(dep_id)
            if not dep:
                lines.append(f"- {dep_id}: (not yet run)")
                continue
            lines.append(f"- {dep_id} ({dep.get('status')}): {dep.get('summary', '')[:400]}")
        return "\n".join(lines)

    def postprocess(self, env: AgentEnvelope, state: RunState) -> AgentEnvelope:
        """Enforce tool permissions — strip patches/tests if not allowed."""
        tools = set(self.spec.get("tools", []))
        if "all" in tools:
            return env
        if "patch" not in tools and "write" not in tools:
            if env.patches:
                log.warning(
                    "agent %s produced patches without patch/write permission; dropping",
                    self.spec["id"],
                )
                env.patches = {}
        if "write_test" not in tools:
            if env.tests:
                log.warning(
                    "agent %s produced tests without write_test permission; dropping",
                    self.spec["id"],
                )
                env.tests = {}
        return env
