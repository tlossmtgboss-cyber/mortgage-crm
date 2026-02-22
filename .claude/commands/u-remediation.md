---
name: u-remediation
description: >
  Comprehensive remediation skill for Perennia AI mortgage CRM platform. Use this skill whenever
  working on Perennia AI codebase improvements including: test coverage, CI/CD setup, architecture
  refactoring (main.py decomposition, monolithic file splitting, API consolidation), Encompass LOS
  integration, telephony consolidation, frontend accessibility, component reorganization, SOC 2
  preparation, feature deprecation/focus strategy, database migration tooling, or any task related
  to the critical findings from the February 2026 platform audit. Trigger on any mention of
  fixing tech debt, improving platform health score, remediation, audit findings, or codebase
  quality improvements for Perennia AI / Pipeline 360.
version: 1.0.0
author: TL Development LLC
target: Perennia AI Platform (all layers)
---

# Perennia AI — Systematic Remediation Skill

This skill provides a structured, prioritized playbook for resolving all critical findings from the
February 2026 Devil's Advocate audit. Every recommendation is concrete, sequenced to minimize risk,
and designed for a solo/micro-team to execute incrementally.

## How to Use This Skill

1. **Identify which remediation area** the current task falls under (see Priority Tiers below)
2. **Read the relevant reference file** before writing any code
3. **Follow the checklist** in the reference file — each has step-by-step instructions
4. **Run the validation script** after completing each phase (see `scripts/validate_phase.sh`)

## Priority Tiers

### TIER 1 — Critical (Week 1–2)

| # | Issue | Reference File | Est. Effort |
|---|-------|---------------|-------------|
| 1 | CI/CD + Test Coverage (effectively 0%) | `references/testing.md` | 1–2 weeks |
| 2 | Feature Focus & Deprecation Strategy | `references/focus-strategy.md` | 1 day decision + ongoing |
| 3 | Encompass LOS Integration | `references/encompass-integration.md` | 4–8 weeks |

### TIER 2 — Important (Week 2–6)

| # | Issue | Reference File | Est. Effort |
|---|-------|---------------|-------------|
| 4 | main.py Dependency Graph Breakup | `references/architecture.md` § main.py | 2–3 weeks |
| 5 | Monolithic File Splitting | `references/architecture.md` § monoliths | 2 weeks |
| 6 | Telephony Provider Consolidation | `references/telephony.md` | 1–2 weeks |
| 7 | Frontend Accessibility Baseline | `references/frontend.md` § accessibility | 2–3 weeks |
| 8 | API Endpoint Consolidation | `references/architecture.md` § api-consolidation | 2–3 weeks |

### TIER 3 — Next Quarter (Month 2–3)

| # | Issue | Reference File | Est. Effort |
|---|-------|---------------|-------------|
| 9 | SOC 2 Type I Preparation | `references/security-compliance.md` | 3–6 months |
| 10 | Spanish-Language Portal (i18n) | `references/frontend.md` § i18n | 3–4 weeks |
| 11 | AI Agent Value Metrics Dashboard | `references/ai-agents.md` | 2 weeks |
| 12 | Migration Tooling (Alembic autogen) | `references/architecture.md` § migrations | 1–2 weeks |
| 13 | Frontend Component Reorganization | `references/frontend.md` § organization | 2 weeks |

## Decision Framework

When starting a remediation task, ask:

1. **Does it unblock revenue?** → Encompass integration, SOC 2
2. **Does it prevent production incidents?** → CI/CD, test coverage, data integrity
3. **Does it reduce maintenance burden?** → main.py breakup, file splitting, API consolidation
4. **Does it improve user experience?** → Accessibility, i18n, workflow efficiency
5. **Does it prove value?** → AI agent metrics dashboard

Always prioritize items higher on this list. Never start a Tier 3 item while Tier 1 items remain unfinished.

## Reference Files

Read the relevant reference file BEFORE writing any code:

- `references/testing.md` — CI/CD pipeline setup, test strategy, coverage targets
- `references/architecture.md` — main.py decomposition, monolith splitting, API consolidation, migrations
- `references/encompass-integration.md` — Encompass Developer Connect API integration guide
- `references/telephony.md` — Provider consolidation playbook (Twilio vs Telnyx)
- `references/frontend.md` — Accessibility, component reorganization, i18n
- `references/focus-strategy.md` — Feature deprecation framework, core vs non-core classification
- `references/security-compliance.md` — SOC 2 preparation, data integrity, audit trails
- `references/ai-agents.md` — Tool registry bridging, agent metrics, value demonstration

## Validation

After completing any phase, run:
```bash
python scripts/validate_phase.sh <phase-name>
```

This checks that the remediation was applied correctly and hasn't introduced regressions.
