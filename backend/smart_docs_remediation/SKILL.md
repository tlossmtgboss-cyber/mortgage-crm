---
name: perennia-smart-docs-remediation
description: >
  Run a 100-agent LangGraph remediation program against the Perennia
  Smart Docs subsystem. Triggers on requests to fix, audit, remediate,
  or harden Smart Docs; to address findings from the Smart Docs critical
  analysis report; or to coordinate parallel Claude-powered agents
  against that 80-service / 25-route / 24K-LOC codebase. The program
  scans the codebase, produces patches, migrations, and tests per
  finding, gates high-risk changes behind human approval (M99), and
  emits a final run report keyed by agent id.
license: Proprietary — TL Development LLC
---

# Perennia AI — Smart Docs Remediation Skill

A 100-agent swarm that systematically addresses every finding in the
Smart Docs critical analysis report. Built on LangGraph, orchestrated
against Claude Opus 4.7 (for high-risk reasoning) and Claude Sonnet
4.5 (for scanning and routine patch generation).

## When to use this skill

Invoke when:

- The operator asks to fix, audit, remediate, or harden Smart Docs.
- A new finding must be slotted into the existing remediation DAG.
- The operator wants a status report on an in-flight run.
- A patch needs to be rolled back or an approval needs to be revisited.

Do **not** invoke this skill to write arbitrary Smart Docs features or
to onboard new integrations — the skill is scoped to the 21 findings in
the report plus the 10 meta-orchestration agents.

## Topology

The swarm is structured as four tiers matching the report's
prioritization:

| Tier      | Count | Purpose                                         |
|-----------|-------|-------------------------------------------------|
| critical  |  30   | Ship-blockers. Data integrity, secrets, TCPA. |
| important |  40   | UX, perf, resilience.                           |
| consider  |  20   | Migration hygiene, analytics foundation.        |
| meta      |  10   | Coordinator, resolver, gates, observer.         |

Every agent has a unique id (`A01`–`A90`, `M91`–`M100`), a mission,
explicit dependencies, and tool permissions declared in
[`config/agents.yaml`](config/agents.yaml).

## Running the program

### Quickstart

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...

# Dry run against a local Perennia checkout — produces patches + tests
# in fixes/ but does not apply them.
python -m orchestrator.runner --codebase ~/perennia --all

# Run only the Critical tier for Findings #1, #2, #3:
python -m orchestrator.runner --codebase ~/perennia --findings 1,2,3

# Apply patches after review:
python -m orchestrator.runner --codebase ~/perennia --all --apply
```

### Dashboard

`dashboard/index.html` is a single-file control plane. In production it
fetches `GET /api/remediation/runs/:run_id/state` and subscribes to the
SSE stream at `GET /api/remediation/runs/:run_id/stream`. Open it
directly in a browser to see the preview with mock data.

## Extending the program

### Adding a new agent

1. Append a new entry to `config/agents.yaml` with a unique id (next
   free slot is `A91`).
2. If the agent warrants specialist guardrails (schema changes,
   security, compliance), subclass `BaseAgent` in
   `agents/critical/`, `agents/important/`, or `agents/consider/` and
   register it in `agents/registry.py::SPECIALIST_CLASSES`.
3. If the agent is a plain "read, reason, produce envelope" worker,
   do nothing else — it will be picked up by `GenericAgent`.

### Invariants the program enforces

- **Dependency acyclicity** — M92 runs Kahn's algorithm at plan time.
  A cycle aborts the run loud rather than deadlocking.
- **Tool permissions** — agents declaring `tools: [read]` cannot emit
  patches. `GenericAgent.postprocess` strips unauthorized outputs.
- **Human-in-the-loop** — agents with `autonomy: human_approval` OR
  `risk: high` pause at M99 with a structured approval request.
- **Deny-by-default on consent** — A30's postprocess refuses to ship
  a gateway that returns `allowed=True` without also exercising the
  `allowed=False` path.
- **Fail-closed on security** — A26's postprocess refuses any patch
  that still references the old `not_screenshot` default in the
  except branch.

## Mapping findings to agents

Every finding in the report (#1 – #21) is touched by at least one
agent; no finding goes unaddressed. The full mapping lives in
`config/agents.yaml` under each agent's `finding_refs`. Quick
reference:

| Finding | Title                                          | Agents |
|---------|------------------------------------------------|--------|
| #1      | Document ID vs Request ID confusion            | A01–A08 |
| #2      | Inconsistent API response schema               | A09–A13 |
| #3      | Partial failure with no recovery               | A14–A18 |
| #4      | requires_esign dead code                       | A19–A21 |
| #5      | Hardcoded SECRET_KEY fallback                  | A22–A25 |
| #6      | TCPA consent fragmentation                     | A29, A30, A82–A84, A90 |
| #7      | 25 route files / consolidation                 | A36–A38, A42, A43 |
| #8      | Enterprise services on a wobbly foundation     | A39–A41, A67–A70 |
| #9      | Sequential bulk operations                     | A44–A46 |
| #10     | In-memory query filtering                      | A62–A66 |
| #11     | Screenshot detection fails open                | A26–A28 |
| #12     | No multi-page PDF support                      | A31–A35 |
| #13     | No error boundaries                            | A47–A49, A87 |
| #14     | No optimistic UI or real-time updates          | A50–A54, A86 |
| #15     | No offline / network resilience                | A55–A59, A35 |
| #16     | Bulk merge silent failure                      | A04, A60, A61 |
| #17     | 36K-line migration script                      | A71–A75 |
| #18     | Enterprise before core                         | A36, A37, A39, A40 |
| #19     | 6 consent / compliance surfaces                | A29, A30, A82–A84 |
| #20     | Analytics before adoption                      | A79–A81, A85, A88, A89 |
| #21     | Follow-up campaign engine duplication          | A76–A78 |

## File layout

```
smart-docs-remediation/
├── SKILL.md                    ← this file
├── README.md                   ← detailed operator guide
├── requirements.txt
├── config/
│   └── agents.yaml             ← canonical 100-agent registry
├── orchestrator/
│   ├── graph.py                ← LangGraph state machine
│   ├── state.py                ← RunState TypedDict
│   └── runner.py               ← CLI entrypoint
├── agents/
│   ├── base.py                 ← BaseAgent + GenericAgent
│   ├── registry.py             ← YAML loader + factory
│   ├── critical/__init__.py    ← A07, A23, A26, A30 specialists
│   ├── important/              ← (GenericAgent handles; extend as needed)
│   ├── consider/               ← (GenericAgent handles; extend as needed)
│   └── meta/__init__.py        ← M91, M92, M93, M99, M100
├── tools/
│   ├── codebase_scanner.py     ← read, grep, ast_walk, log_query
│   └── patch_generator.py      ← validate, apply, revert (git-backed)
├── dashboard/
│   └── index.html              ← single-file control plane
└── fixes/
    └── patches/                ← generated patches land here
```

## Deployment notes

- The program is stateless between runs; replaying the same run id is
  safe.
- Patch files are git-validated (`git apply --check`) before any
  mutation. In dry-run mode (default) nothing is applied to the
  working tree.
- M98 (rollback manager) stores a revert patch for every applied
  patch. Post-deploy health failures trigger automatic rollback.
- The dashboard is static; it expects a control-plane REST endpoint
  at `/api/remediation/*`. Wire that up inside the Perennia FastAPI
  app when ready.

## Versioning

Program v1.0.0. Agent YAML v1.0.0. Both are versioned independently;
a minor bump to the YAML that adds agents without changing existing
ids is backwards-compatible.
