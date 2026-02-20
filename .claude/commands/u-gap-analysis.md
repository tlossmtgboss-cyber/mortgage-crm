---
name: u-gap-analysis
description: >
  Master operational skill for Perennia AI that fills every identified gap across
  all 20 agents and 160 tools. Covers 13 modules across 4 phases: mortgage compliance
  engine, conversation memory & context, escalation & handoff protocol, document
  intelligence, channel communication adapter, referral & partner management, rate
  intelligence & market advisory, workflow automation triggers, refinance intelligence,
  onboarding & training, reporting & analytics intelligence, LOS integration & sync,
  and marketing campaign orchestration. Use this skill whenever ANY agent needs
  governing intelligence beyond basic tool execution.
version: 1.0.0
author: TL Development LLC
target_agents: ALL (20 agents)
---

# /u-gap-analysis — Perennia AI Master Operational Skill

> Every agent has tools. This skill gives them judgment.

## How This Skill Works

This skill is organized into 13 modules across 4 phases. Each module provides:
1. **Decision Rules** — When to act, when to wait, when to escalate
2. **Execution Protocols** — Step-by-step procedures for complex scenarios
3. **Guardrails** — Hard limits that cannot be overridden
4. **Integration Points** — How this module connects to other agents/tools
5. **Self-Check Protocol** — What the agent verifies before responding

**Module Loading Rules:**
- Modules 1-3 (Compliance, Memory, Escalation) → ALWAYS loaded for ALL agents
- Modules 4-13 → Loaded when intent matches module domain

## Agent-to-Module Mapping

```
CORE CRM:
  Pipeline Analyst      → 1,2,3 + 8,11
  Compliance Checker    → 1,2,3 (Module 1 PRIMARY)
  Lead Nurturer         → 1,2,3 + 7,8,9,13
  Document Tracker      → 1,2,3 + 4
  Profitability Analyst → 1,2,3 + 11
  Rate Advisor          → 1,2,3 + 6,9
  Team Coach            → 1,2,3 + 11
  Customer Intelligence → 1,2,3 + 7,9

COMMUNICATION:
  Voice OS              → 1,2,3 + 5
  UVIP                  → 1,2,3 + 5
  Email Intelligence    → 1,2,3 + 4,5,13
  AI Receptionist       → 1,2,3 + 5 (Module 3 PRIMARY)

OPERATIONS:
  Smart Scheduler       → 1,2,3
  Task Automation       → 1,2,3 + 8 (Module 8 PRIMARY)
  SLA Tracker           → 1,2,3 + 8
  Integrations          → 1,2,3 + 12 (Module 12 PRIMARY)

BUSINESS:
  Reporting             → 1,2,3 + 11 (Module 11 PRIMARY)
  Notifications         → 1,2,3 + 5,8
  Subscription          → 1,2,3 + 10
  Onboarding            → 1,2,3 + 10 (Module 10 PRIMARY)
```

For complete module specifications, see IMPLEMENTATION.md
