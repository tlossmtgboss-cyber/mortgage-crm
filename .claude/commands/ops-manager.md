---
name: ops-manager
description: >
  AI Operations Manager — Deterministic pipeline enforcement and orchestration layer for
  Perennia AI mortgage CRM. Evaluates every loan against policy-as-code, manages exception
  lifecycles, enforces stage transition governance, generates daily priority queues, and
  monitors SLA compliance. Produces role-specific execution queues (Must Today / Should Today
  / Strategic) with AI advisory overlay. Use this skill for pipeline health checks, exception
  management, stage transition evaluation, priority queue generation, staffing gap detection,
  lock risk monitoring, SLA enforcement, and operational cadence management. Triggers on:
  'ops manager', 'pipeline sweep', 'pipeline health', 'exception', 'impediment', 'staffing gap',
  'stage transition', 'priority queue', 'daily brief', 'SLA breach', 'lock expiring',
  'missing processor', 'missing closer', 'unassigned loan', 'ops brief', 'what needs to be done'.
version: 2026.03.02.v1
author: TL Development LLC
target: Perennia AI Platform — Loan Pipeline Operations
---

# /ops-manager — AI Operations Manager

> **Deterministic enforcement + AI advisory overlay for mortgage pipeline operations.**

This skill governs the mortgage file lifecycle from lead through funding by enforcing
rules—not doing the work. It eliminates operational drift (unassigned files, skipped steps,
missed SLAs, late disclosures/CDs, expiring locks) by making staffing, stage transitions,
milestones, and SLA timing deterministic and auditable.

## How to Use

```
/ops-manager                        # Full pipeline health evaluation
/ops-manager loan 12345             # Single loan health check
/ops-manager daily brief            # Generate today's priority queue
/ops-manager sweep                  # Run full pipeline sweep
/ops-manager exceptions             # View all open exceptions
/ops-manager transition eval 12345  # Evaluate stage transition readiness
```

## What It Does

| Capability | Description |
|------------|-------------|
| **Loan Snapshot Evaluation** | Evaluates every loan against all active policy rules |
| **Exception Lifecycle** | Creates, routes, escalates, snoozes, and resolves exceptions |
| **Stage Transition Gating** | Validates transition requests against governance policy |
| **Daily Priority Queue** | Generates MustToday / ShouldToday / Strategic work queues |
| **SLA Enforcement** | Monitors milestone due dates and triggers escalation chains |
| **Staffing Monitor** | Detects coverage gaps and raises staffing exceptions |
| **Lock Risk Detection** | Monitors rate lock expirations and creates LockRisk exceptions |
| **AI Suggestions** | Creates advisory suggestions for optimization opportunities |

## Policy Configuration

Policy rules are defined in `policy_config.yaml` and include:
- **Stage Transitions**: Required roles, milestones, and blocking exception types
- **SLA Policies**: Time-bound obligations triggered by field changes
- **Staffing Rules**: Required role assignments per stage
- **Data Integrity Rules**: Field consistency checks
- **Lock Risk Rules**: Rate lock expiration monitoring
- **Milestone Presence Rules**: Required milestone completion per stage
- **Priority Scoring**: Weights for exception prioritization

## Exception Types

| Type | Description |
|------|-------------|
| SLA | SLA milestone overdue or at risk |
| Staffing | Required role not assigned |
| Guideline | Underwriting or product guideline violation |
| DataIntegrity | Field-level inconsistency or missing data |
| LockRisk | Rate lock expiring soon |
| Compliance | Regulatory requirement not met |

## Output Formats

- **Exception Summary**: `[SEVERITY] Type: description — Loan #XXX — Owner: name`
- **Daily Ops Brief**: Prioritized queue with Must Today / Should Today / Strategic buckets
- **Loan Health Report**: Comprehensive health check with exceptions, milestones, roles, risk score

---

*See SKILL.md and policy_config.yaml in ~/.claude/skills/ops-manager/ for complete specifications.*
