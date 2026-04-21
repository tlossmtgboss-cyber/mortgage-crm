# 09 — AI Tool Loading (Dynamic, Role-Scoped)

**Addresses:** Over-engineering observation — 255 AI tools, "Many are similar (slight variations on lead/loan queries). Could consolidate to ~80."

## Why We're NOT Consolidating

The audit's recommendation to merge tools into ~80 parameterized versions is directionally reasonable but has real costs that the audit didn't weigh:

1. **Tool routing accuracy degrades with parameterization.** Claude routes better when tool names and descriptions are specific. `get_loan_by_stage` + `get_loan_by_assignee` + `get_loan_by_tag` route more reliably than `get_loan(filter_type, filter_value)`. Anthropic's guidance is one-tool-one-job.
2. **Behavior contracts are clearer.** `schedule_borrower_follow_up` has a narrower contract than `schedule_task(task_type="borrower_follow_up")`. Easier to evaluate, easier to red-team.
3. **Context window is the real enemy, not tool count.** 255 tools × ~80 tokens of schema = ~20k tokens just for schemas, every query. That's the problem worth solving.

## The Real Fix: Load Tools Dynamically Per Agent

Instead of flattening 255 → 80, load the right ~25-40 for each agent invocation based on (role, task). The full registry stays — the context window doesn't.

## Architecture

```
┌──────────────────┐     ┌────────────────────┐     ┌──────────────────┐
│  Agent request   │────>│   Tool Router      │────>│  Claude API      │
│  (role, intent)  │     │  (selects subset)  │     │  (with ~30 tools)│
└──────────────────┘     └────────────────────┘     └──────────────────┘
                                   │
                                   v
                         ┌────────────────────┐
                         │  Tool Registry     │
                         │  (all 255 tools    │
                         │  tagged by role,   │
                         │  domain, intent)   │
                         └────────────────────┘
```

## Components

1. **`registry.py`** — canonical tool definitions with metadata (domain, roles, intents)
2. **`router.py`** — given (role, intent, recent context), returns 25-40 tools
3. **`usage_tracker.py`** — Redis-backed popularity tracking; tools that never get called become candidates for deprecation
4. **`evaluator.py`** — eval harness that replays real agent sessions against candidate tool subsets and compares routing accuracy

## Measured Targets

- **Context window for tool schemas:** drop from ~20k tokens to <5k tokens per call
- **Routing accuracy:** hold ≥95% vs. full-registry baseline (measured via `evaluator.py`)
- **p50 latency:** drop 200-400ms from smaller prompt size

## Deprecation Process

Tools with <5 invocations/month for 3 consecutive months get flagged in a monthly report. Review → either mark as deprecated (emits warning when called) or delete after one more month of zero usage.
