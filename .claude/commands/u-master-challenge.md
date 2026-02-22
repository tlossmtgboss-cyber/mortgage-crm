---
name: u-master-challenge
description: >
  Unified master challenge that orchestrates ALL 19 Perennia AI skills into a single
  platform-wide assessment. Runs 6 challenge domains covering enterprise readiness,
  engineering quality, AI agent fleet, call intelligence, workflow integrity, and
  portal/security — producing a consolidated Platform Health Score with grade
  certification. Use this skill for full platform audits, pre-release certification,
  investor-ready health checks, or targeted domain deep-dives. Triggers on:
  'master challenge', 'full platform audit', 'platform health', 'certification run',
  'run all challenges', 'platform score', 'comprehensive audit'.
version: 1.0.0
author: TL Development LLC
target: Perennia AI Platform (all layers)
---

# /u-master-challenge — Unified Platform Health & Certification Engine

> One skill to run them all. 19 skills. 6 domains. 1 score.

## Purpose

This master challenge orchestrates every Perennia AI skill into a single execution
pipeline. It loads each constituent skill, runs its checks, collects scores, and
rolls everything into a unified Platform Health Score with pass/fail certification.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    MASTER CHALLENGE RUNNER                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  DOMAIN 1          DOMAIN 2          DOMAIN 3                   │
│  Platform &        Engineering       AI Agent                   │
│  Enterprise        Quality           Fleet                      │
│  ┌──────────┐     ┌──────────┐     ┌──────────┐               │
│  │enterprise│     │engineer- │     │u_agent_  │               │
│  │-readiness│     │ing-disci-│     │challenge │               │
│  │          │     │pline-    │     │u_agent_  │               │
│  │u-multi-  │     │challenge │     │audit     │               │
│  │tenant-   │     │          │     │u_agent_  │               │
│  │challenge │     │code-     │     │fleet     │               │
│  │          │     │evaluator │     │agent_opt │               │
│  └──────────┘     └──────────┘     │u-gap-    │               │
│   Weight: 25%      Weight: 20%     │analysis  │               │
│                                    └──────────┘               │
│  DOMAIN 4          DOMAIN 5         Weight: 20%               │
│  Call              Workflow &                                   │
│  Intelligence      Data Integrity   DOMAIN 6                   │
│  ┌──────────┐     ┌──────────┐     Portal,                    │
│  │call-     │     │u-workflow│     Security                    │
│  │intellig- │     │-challenge│     & Content                   │
│  │ence-     │     │          │     ┌──────────┐               │
│  │challenge │     │loan-state│     │portal-   │               │
│  │          │     │-reconcil-│     │skill-    │               │
│  └──────────┘     │iation    │     │challenge │               │
│   Weight: 15%     │          │     │          │               │
│                   │crm-work- │     │u-challen-│               │
│                   │flow-audit│     │ge        │               │
│                   └──────────┘     │          │               │
│                    Weight: 10%     │hallucin- │               │
│                                    │ation-    │               │
│                                    │detector  │               │
│                                    └──────────┘               │
│                                     Weight: 10%               │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│  SCORING: Domain scores → Weighted average → Platform Score     │
│  GRADE:   A (90+) | B (80-89) | C (70-79) | D (60-69) | F (<60)│
│  CERT:    Any domain F → certification blocked                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Execution Modes

When this skill is invoked, determine the execution mode from the user's input:

| Mode | Trigger | What Runs |
|------|---------|-----------|
| **Full** | `/u-master-challenge` or `/u-master-challenge full` | All 6 domains in sequence |
| **Domain** | `/u-master-challenge domain:<name>` | Single domain only |

Valid domain names: `platform`, `engineering`, `agents`, `telephony`, `workflow`, `portal`

If no mode is specified, default to **Full**.

---

## Domain Definitions

### Domain 1: Platform & Enterprise Readiness (Weight: 25%)

**Focus:** Infrastructure maturity, multi-tenant isolation, 12-domain enterprise certification, SaaS scaling readiness.

**Constituent Skills:**
| Skill | File | Weight within Domain |
|-------|------|---------------------|
| `enterprise-readiness` | `.claude/commands/enterprise-readiness.md` | 65% |
| `u-multi-tenant-challenge` | `.claude/commands/u-multi-tenant-challenge.md` | 35% |

**Execution:**
1. Read and execute `.claude/commands/enterprise-readiness.md` — run its 12-domain certification audit
2. Read and execute `.claude/commands/u-multi-tenant-challenge.md` — run its 8-domain SaaS validation
3. Compute domain score: `(enterprise_score × 0.65) + (multi_tenant_score × 0.35)`

---

### Domain 2: Engineering Quality (Weight: 20%)

**Focus:** Code quality, anti-pattern detection, 7 failure pillars, systematic code review across Python and TypeScript.

**Constituent Skills:**
| Skill | File | Weight within Domain |
|-------|------|---------------------|
| `engineering-discipline-challenge` | `.claude/commands/engineering-discipline-challenge.md` | 60% |
| `code-evaluator` | `.claude/commands/code-evaluator.md` | 40% |

**Execution:**
1. Read and execute `.claude/commands/engineering-discipline-challenge.md` — assess the 7 failure pillars
2. Read and execute `.claude/commands/code-evaluator.md` — run systematic code review checklists
3. Compute domain score: `(discipline_score × 0.60) + (evaluator_score × 0.40)`

---

### Domain 3: AI Agent Fleet (Weight: 20%)

**Focus:** Agent performance, fleet health, optimization opportunities, gap coverage across all 20 agents and 160 tools.

**Constituent Skills:**
| Skill | File | Weight within Domain |
|-------|------|---------------------|
| `u_agent_challenge` | `.claude/commands/u_agent_challenge.md` | 25% |
| `u_agent_audit` | `.claude/commands/u_agent_audit.md` | 25% |
| `u_agent_fleet` | `.claude/commands/u_agent_fleet.md` | 20% |
| `agent_optimization_framework` | `.claude/commands/agent_optimization_framework.md` | 15% |
| `u-gap-analysis` | `.claude/commands/u-gap-analysis.md` | 15% |

**Execution:**
1. Read and execute `.claude/commands/u_agent_challenge.md` — run challenge scenarios against agents
2. Read and execute `.claude/commands/u_agent_audit.md` — audit agent performance and configuration
3. Read and execute `.claude/commands/u_agent_fleet.md` — fleet-wide cross-optimization analysis
4. Read and execute `.claude/commands/agent_optimization_framework.md` — optimization recommendations
5. Read and execute `.claude/commands/u-gap-analysis.md` — identify coverage gaps across all agents
6. Compute domain score: `(challenge × 0.25) + (audit × 0.25) + (fleet × 0.20) + (optimization × 0.15) + (gap × 0.15)`

---

### Domain 4: Call Intelligence & Telephony (Weight: 15%)

**Focus:** 11 telephony domains, 100+ checks, provider health, compliance, AI voice workflows.

**Constituent Skills:**
| Skill | File | Weight within Domain |
|-------|------|---------------------|
| `call-intelligence-challenge` | `.claude/commands/call-intelligence-challenge.md` | 100% |

**Execution:**
1. Read and execute `.claude/commands/call-intelligence-challenge.md` — run all 11 telephony domain checks
2. Domain score = skill score directly

---

### Domain 5: Workflow & Data Integrity (Weight: 10%)

**Focus:** SLA tracking, pipeline state reconciliation, task generation, workflow routing, CRM automation.

**Constituent Skills:**
| Skill | File | Weight within Domain |
|-------|------|---------------------|
| `u-workflow-challenge` | `.claude/commands/u-workflow-challenge.md` | 40% |
| `loan-state-reconciliation` | `.claude/commands/loan-state-reconciliation.md` | 35% |
| `crm-workflow-audit` | `~/.claude/skills/crm-workflow-audit/SKILL.md` | 25% |

**Execution:**
1. Read and execute `.claude/commands/u-workflow-challenge.md` — validate SLA-driven task generation
2. Read and execute `.claude/commands/loan-state-reconciliation.md` — verify loan state transitions
3. Read and execute `~/.claude/skills/crm-workflow-audit/SKILL.md` — audit CRM workflow routing
4. Compute domain score: `(workflow × 0.40) + (reconciliation × 0.35) + (crm_audit × 0.25)`

---

### Domain 6: Portal, Security & Content (Weight: 10%)

**Focus:** Portal validation, project-level critical analysis, content accuracy and hallucination detection.

**Constituent Skills:**
| Skill | File | Weight within Domain |
|-------|------|---------------------|
| `portal-skill-challenge` | `.claude/commands/portal-skill-challenge.md` | 40% |
| `u-challenge` | `~/.claude/skills/u-challenge/SKILL.md` | 30% |
| `hallucination-detector` | `~/.claude/skills/hallucination-detector/SKILL.md` | 30% |

**Execution:**
1. Read and execute `.claude/commands/portal-skill-challenge.md` — validate portal systems
2. Read and execute `~/.claude/skills/u-challenge/SKILL.md` — run critical project analysis
3. Read and execute `~/.claude/skills/hallucination-detector/SKILL.md` — verify content accuracy
4. Compute domain score: `(portal × 0.40) + (critique × 0.30) + (hallucination × 0.30)`

---

## Scoring System

### Per-Skill Scoring

Each skill produces its own score on a 0-100 scale using its internal rubric. If a skill uses a different scale (e.g., 0-10), normalize to 0-100 by multiplying by 10.

### Domain Scoring

Domain score = weighted average of constituent skill scores (weights defined above per domain).

### Platform Score

```
Platform Score = (Domain1 × 0.25) + (Domain2 × 0.20) + (Domain3 × 0.20)
               + (Domain4 × 0.15) + (Domain5 × 0.10) + (Domain6 × 0.10)
```

### Grade Scale

| Grade | Score Range | Certification Status |
|-------|-------------|---------------------|
| **A** | 90 – 100 | CERTIFIED — Enterprise-ready |
| **B** | 80 – 89 | PROVISIONAL — Minor remediation needed |
| **C** | 70 – 79 | CONDITIONAL — Significant gaps, not client-ready |
| **D** | 60 – 69 | AT RISK — Major remediation required |
| **F** | 0 – 59 | FAILED — Critical deficiencies |

### Certification Rules

- **Any single domain scoring F (< 60)** → overall certification is **BLOCKED** regardless of Platform Score
- **Two or more domains scoring D** → overall grade capped at **C**
- **All domains B or above** → eligible for full certification

---

## Execution Protocol

Follow this exact sequence when running the master challenge:

### Phase 1: Initialization
1. Print the master challenge header with timestamp
2. Determine execution mode (full or single domain)
3. List all domains and skills that will be executed

### Phase 2: Domain Execution
For each domain (in order 1 through 6, or single domain if specified):

1. **Announce** the domain: print domain name, weight, and constituent skills
2. **Load** each constituent skill by reading its file
3. **Execute** the skill's checks against the codebase — follow the skill's own instructions for what to inspect, query, or validate
4. **Score** the skill using its internal rubric, normalizing to 0-100
5. **Record** the skill score, key findings, and critical failures
6. **Compute** the domain score using the intra-domain weights
7. **Print** a domain summary before moving to the next

### Phase 3: Scoring & Certification
1. Compute the overall Platform Score using domain weights
2. Determine the grade
3. Apply certification rules (F-block, D-cap)
4. Identify the top 10 priority remediation items across all domains

### Phase 4: Report Generation
Generate the consolidated report in the format defined below.

---

## Report Format

Output the following consolidated report after execution:

```markdown
# Perennia AI — Master Platform Health Report

**Date:** [timestamp]
**Mode:** [Full | Domain: <name>]
**Platform Score:** [XX]/100
**Grade:** [A/B/C/D/F]
**Certification:** [CERTIFIED / PROVISIONAL / CONDITIONAL / AT RISK / BLOCKED]

---

## Executive Summary

[2-3 sentence summary of overall platform health, key strengths, critical gaps]

---

## Domain Scorecard

| # | Domain | Score | Grade | Weight | Weighted | Status |
|---|--------|-------|-------|--------|----------|--------|
| 1 | Platform & Enterprise Readiness | XX/100 | X | 25% | XX.X | [pass/warn/fail] |
| 2 | Engineering Quality | XX/100 | X | 20% | XX.X | [pass/warn/fail] |
| 3 | AI Agent Fleet | XX/100 | X | 20% | XX.X | [pass/warn/fail] |
| 4 | Call Intelligence & Telephony | XX/100 | X | 15% | XX.X | [pass/warn/fail] |
| 5 | Workflow & Data Integrity | XX/100 | X | 10% | XX.X | [pass/warn/fail] |
| 6 | Portal, Security & Content | XX/100 | X | 10% | XX.X | [pass/warn/fail] |
| | **PLATFORM TOTAL** | | **X** | | **XX.X** | |

---

## Critical Failures (Certification Blockers)

[List any findings from ANY domain that are severity=critical. These block certification.]

- [ ] [Domain] — [Description of critical failure]
- [ ] ...

---

## Top 10 Priority Remediations

| # | Domain | Issue | Severity | Estimated Effort | Impact |
|---|--------|-------|----------|-----------------|--------|
| 1 | | | | | |
| ... | | | | | |

---

## Domain Detail: 1 — Platform & Enterprise Readiness

### Skill: enterprise-readiness — Score: XX/100
[Key findings, pass/fail per sub-domain]

### Skill: u-multi-tenant-challenge — Score: XX/100
[Key findings]

---

## Domain Detail: 2 — Engineering Quality

### Skill: engineering-discipline-challenge — Score: XX/100
[Key findings per pillar]

### Skill: code-evaluator — Score: XX/100
[Key findings]

---

## Domain Detail: 3 — AI Agent Fleet

### Skill: u_agent_challenge — Score: XX/100
### Skill: u_agent_audit — Score: XX/100
### Skill: u_agent_fleet — Score: XX/100
### Skill: agent_optimization_framework — Score: XX/100
### Skill: u-gap-analysis — Score: XX/100

---

## Domain Detail: 4 — Call Intelligence & Telephony

### Skill: call-intelligence-challenge — Score: XX/100

---

## Domain Detail: 5 — Workflow & Data Integrity

### Skill: u-workflow-challenge — Score: XX/100
### Skill: loan-state-reconciliation — Score: XX/100
### Skill: crm-workflow-audit — Score: XX/100

---

## Domain Detail: 6 — Portal, Security & Content

### Skill: portal-skill-challenge — Score: XX/100
### Skill: u-challenge — Score: XX/100
### Skill: hallucination-detector — Score: XX/100

---

## Skill Inventory (19 Skills)

| # | Skill | Domain | Location | Score |
|---|-------|--------|----------|-------|
| 1 | enterprise-readiness | Platform | .claude/commands/ | XX |
| 2 | u-multi-tenant-challenge | Platform | .claude/commands/ | XX |
| 3 | engineering-discipline-challenge | Engineering | .claude/commands/ | XX |
| 4 | code-evaluator | Engineering | .claude/commands/ | XX |
| 5 | u_agent_challenge | Agents | .claude/commands/ | XX |
| 6 | u_agent_audit | Agents | .claude/commands/ | XX |
| 7 | u_agent_fleet | Agents | .claude/commands/ | XX |
| 8 | agent_optimization_framework | Agents | .claude/commands/ | XX |
| 9 | u-gap-analysis | Agents | .claude/commands/ | XX |
| 10 | call-intelligence-challenge | Telephony | .claude/commands/ | XX |
| 11 | u-workflow-challenge | Workflow | .claude/commands/ | XX |
| 12 | loan-state-reconciliation | Workflow | .claude/commands/ | XX |
| 13 | crm-workflow-audit | Workflow | ~/.claude/skills/ | XX |
| 14 | portal-skill-challenge | Portal | .claude/commands/ | XX |
| 15 | u-challenge | Portal | ~/.claude/skills/ | XX |
| 16 | hallucination-detector | Portal | ~/.claude/skills/ | XX |

**Total Skills Executed:** 16 unique skill files across 19 registered names
**Note:** `u-challenge` and `u_challenge` reference the same global skill.
```

---

## Special Instructions

### Context Window Management
Running all 19 skills in a single session will generate significant output. To manage this:
- Execute domains sequentially, not in parallel
- For each skill, focus on running its core checks and capturing the score — do not reproduce the full skill output in the report
- Summarize each skill's findings in 3-5 bullet points maximum
- Only include full detail for critical/high severity findings

### Score Normalization
Different skills use different scales:
- Skills scoring 0-100: use directly
- Skills scoring 0-10: multiply by 10
- Skills with pass/fail checks: (passed / total) × 100
- Skills with letter grades: A=95, B=85, C=75, D=65, F=40

### When a Skill Cannot Be Fully Executed
If a skill requires live API calls, database access, or external services that are unavailable:
- Run all static analysis checks that CAN be performed (code inspection, config review, file structure)
- Score based on what was observable
- Note in the report: "Partial execution — [reason]. Score based on static analysis only."

### Deduplication
Some skills overlap in what they check (e.g., both `enterprise-readiness` and `u-multi-tenant-challenge` check tenant isolation). When the same issue is found by multiple skills:
- Count it once in the critical failures list
- Credit each skill independently for finding it
- Do not double-penalize in scoring

---

## Quick Reference: All 19 Skills by Location

### Project Skills (`.claude/commands/`) — 13 files
1. `enterprise-readiness.md`
2. `u-multi-tenant-challenge.md`
3. `engineering-discipline-challenge.md`
4. `code-evaluator.md`
5. `u_agent_challenge.md`
6. `u_agent_audit.md`
7. `u_agent_fleet.md`
8. `agent_optimization_framework.md`
9. `u-gap-analysis.md`
10. `call-intelligence-challenge.md`
11. `u-workflow-challenge.md`
12. `loan-state-reconciliation.md`
13. `portal-skill-challenge.md`

### Global Skills (`~/.claude/skills/`) — 3 directories
14. `u-challenge/SKILL.md`
15. `crm-workflow-audit/SKILL.md`
16. `hallucination-detector/SKILL.md`
