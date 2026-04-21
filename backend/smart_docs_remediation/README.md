# Perennia AI — Smart Docs Remediation

A 100-agent LangGraph program that systematically addresses every
finding in the Smart Docs critical analysis report. Built for Tim /
TL Development LLC.

**Status:** program is scaffolded and validates end-to-end. Agent YAML
parses cleanly (100/100 agents, 21/21 findings covered, zero
dependency cycles). Orchestrator, base agent, four critical
specialists (A07 / A23 / A26 / A30), and five meta agents (M91–M93,
M99, M100) are implemented. The remaining 91 agents run under the
generic YAML-driven path and can be upgraded to specialists on
demand.

---

## Architecture at a glance

```
              ┌─────────────────┐
              │ config/agents   │  ← 100 agents
              │    .yaml        │    (registry)
              └────────┬────────┘
                       │
              ┌────────▼────────┐
              │ AgentRegistry   │  ← instantiates
              │ (agents/...)    │    specialists + GenericAgent
              └────────┬────────┘
                       │
   ┌───────────────────▼───────────────────┐
   │           LangGraph StateGraph        │
   │                                       │
   │   plan ──► dispatch ──► gate ──► ...  │
   │    ▲         │            │           │
   │    │         │            ▼           │
   │    └── topo sort ──  more groups?     │
   │                            │          │
   │                     yes ───┴─── no    │
   │                                │      │
   │                                ▼      │
   │                            finalize   │
   └───────────────────┬───────────────────┘
                       │
              ┌────────▼────────┐
              │ fixes/patches/  │  ← artifacts
              │ state/*.json    │    (disk)
              └─────────────────┘
                       ▲
                       │
              ┌────────┴────────┐
              │ dashboard/      │  ← control plane
              │  index.html     │    (browser)
              └─────────────────┘
```

---

## Quickstart

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...

# Validate the registry (no API calls)
python -c "
from agents.registry import AgentRegistry
from pathlib import Path
r = AgentRegistry(Path('config/agents.yaml'))
print(f'{len(r)} agents loaded')
"

# Dry-run against a local Perennia checkout — produces patches + tests
# in fixes/patches/ but does not apply them.
python -m orchestrator.runner --codebase ~/perennia --all

# Only the Critical tier for Findings #1, #2, #3:
python -m orchestrator.runner --codebase ~/perennia --findings 1,2,3

# Apply patches after you've reviewed them:
python -m orchestrator.runner --codebase ~/perennia --all --apply

# Open the dashboard:
open dashboard/index.html
```

---

## What each tier does

### Critical (30 agents)
Ship-blockers. If these don't merge, Smart Docs has data-integrity
bugs, TCPA exposure, or security holes. High human-approval density.
Opus-weighted for reasoning-critical work (ID contracts, consent
gateway, fail-closed policy).

### Important (40 agents)
UX, performance, and resilience. Multi-page PDF, error boundaries,
real-time updates, offline resilience, SQL-level filtering,
enterprise smoke tests.

### Consider (20 agents)
Migration hygiene (splitting the 36K-line migration, schema diff
tool), analytics foundation, consent schema unification,
follow-up-engine deduplication.

### Meta (10 agents)
Coordinator (M91), dependency resolver (M92), conflict detector
(M93), patch merger (M94), test runner (M95), CI gate (M96), PR
creator (M97), rollback manager (M98), human approver (M99),
observer (M100).

---

## Writing a new specialist agent

For most agents, the YAML entry + `GenericAgent` is enough. Add a
specialist when:

- The agent's output must match a structural invariant (presence of
  certain patch keys, absence of certain anti-patterns).
- The change touches security, compliance, or data integrity and
  should hard-route to human approval.
- Postprocessing needs access to upstream artifacts (e.g. A30 cites
  A29's truth table).

Template:

```python
from agents.base import BaseAgent, AgentEnvelope
from orchestrator.state import RunState

class MySpecialist(BaseAgent):
    SYSTEM = "You are..."

    def build_prompt(self, state: RunState):
        return [
            {"role": "system", "content": self.SYSTEM},
            {"role": "user", "content": "..."},
        ]

    def postprocess(self, env: AgentEnvelope, state: RunState):
        # enforce invariants; set human_approval_needed if violated
        return env
```

Then wire it into `agents/registry.py::SPECIALIST_CLASSES`.

---

## What the program does NOT do (yet)

- **Live GitHub PR creation** — M97 is scaffolded but calls a stub;
  wire to `gh` CLI or the GitHub API when ready.
- **Sentry integration on orchestrator failures** — the agents that
  patch into Sentry on the app side exist (A48), but the orchestrator
  itself logs to stdout only.
- **Specialist agents for every important/consider tier entry** —
  A54 (optimistic locking), A72 (migration savepoints), A83 (consent
  backfill) are prime candidates. For now they run as GenericAgent
  with `autonomy: human_approval`.
- **Real-time dashboard streaming** — the dashboard renders from
  static mock data. Add an SSE subscriber when the control-plane
  endpoint exists.

---

## Known invariants

- 100 agents. 21 findings. 0 cycles. 6 parallel groups.
- Max parallelism: 39 agents concurrent (group 1).
- Specialists enforce: A07 requires both Python + TS patches; A23
  always escalates to human review; A26 requires `NEEDS_REVIEW`
  default; A30 enforces deny-by-default.
- Patch files live under `fixes/patches/<AGENT_ID>__<sanitized_path>.patch`.
- Run state lives under `state/run_<run_id>.json`.
