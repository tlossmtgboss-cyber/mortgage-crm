# Agent Challenge — CI Integration

This package wires the existing `backend/agents/tools/u_agent_challenge.py`
framework into CI as a **nightly regression baseline** and a **per-PR
regression gate**.

The underlying framework (scenario library, LLM-as-judge scoring, prompt
patch generator) is left untouched. This directory only adds:

| File | Purpose |
|---|---|
| `runner.py` | CLI adapter: runs the suite, emits a stable JSON report, diffs against baseline. |
| `baseline.json` | Captured regression baseline. Updated only via reviewed PR. |
| `__init__.py` | Package marker. |

---

## How scoring works

`ScoringEngine` scores every challenge response across **six dimensions**
using Claude as a judge:

- `accuracy`
- `compliance`
- `tone`
- `tool_usage`
- `efficiency`
- `adaptability`

Each scenario produces a composite score (0–100) and a list of
**violations**. Violations of type `compliance` are treated as
**critical**; everything else defaults to `warning`.

The CI runner aggregates these into a stable schema:

```jsonc
{
  "schema_version": "1.0",
  "timestamp": "...",
  "status": "ran" | "skipped" | "placeholder",
  "overall_score": 87.4,          // weighted mean of per-agent avg_score
  "per_agent_scores": { "pipeline_analyst": 91.2, ... },
  "per_compliance_pillar": {
    "accuracy": 88.1, "compliance": 94.0, "tone": 86.5,
    "tool_usage": 81.0, "efficiency": 79.4, "adaptability": 83.2
  },
  "failures": [
    { "agent": "...", "challenge": "...", "type": "...",
      "severity": "critical" | "warning", "detail": "..." }
  ],
  "regressions": [ ... ]
}
```

---

## What triggers a regression

The PR gate (and nightly job) exits **non-zero** if **any** of:

1. **Overall score drops more than 2 points** vs baseline.
2. **Any compliance pillar drops more than 5 points** vs baseline.
   (All six dimensions in `per_compliance_pillar` are checked.)
3. **Any NEW critical-severity failure** appears that wasn't present in
   the baseline. (Keyed by `(agent, challenge, type)`.)

If the baseline's `overall_score` is `null` (placeholder state), the
regression check is skipped — the first real nightly run produces the
first comparable snapshot.

---

## How to update the baseline

Baselines move **only via reviewed PR**. The procedure:

1. Trigger a clean run on `main`:
   ```bash
   python3 -m backend.agents.challenge.runner \
     --output json --write backend/agents/challenge/baseline.json
   ```
   (Or download `challenge-report.json` from the most recent successful
   `Agent Challenge Nightly` run and copy it to `baseline.json`.)

2. Open a PR titled `chore(agents): refresh challenge baseline`.

3. The PR description must include:
   - Reason for the refresh (planned prompt rollout, scenario library
     update, agent additions, etc.).
   - Diff summary of `overall_score` and `per_compliance_pillar`.
   - Confirmation that no failure regressed silently.

4. At least one reviewer from the Agents team must approve before merge.

Never amend the baseline as part of an unrelated PR — it defeats the
purpose of the regression check.

---

## How to skip a failing scenario

If a scenario is known-broken and a fix is in flight, mark it with the
`# noqa: challenge-skip` marker in the scenario definition inside
`backend/agents/tools/u_agent_challenge.py`:

```python
ChallengeScenario(
    id="pipeline_analyst_velocity_q3",
    # noqa: challenge-skip — flaky against staging API; tracked in JIRA AGT-2210
    title="Q3 velocity report",
    ...
)
```

The marker is a documentation convention recognized by the agents team;
the scenario will still execute, but its violations are deliberately
excluded from the baseline refresh until the marker is removed. Do not
leave skips in place for more than one sprint without a tracking issue.

---

## Running locally

```bash
# Dry run (no creds → structured skip, exit 0):
python3 -m backend.agents.challenge.runner --output text

# Full run, compare against baseline:
ANTHROPIC_API_KEY=sk-... PERENNIA_API_PASS=... \
  python3 -m backend.agents.challenge.runner \
    --output json --baseline backend/agents/challenge/baseline.json
```

Use `--require-run` if you want the CLI to exit `2` when credentials are
missing instead of skipping silently (useful for manual investigations).
