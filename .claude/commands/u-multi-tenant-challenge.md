---
name: u-multi-tenant-challenge
description: >
  Comprehensive multi-tenant SaaS readiness validation for Perennia AI. Use this skill
  whenever validating tenant isolation, licensing infrastructure, subscription management,
  scaling readiness, white-label support, usage metering, or any aspect of preparing the
  platform for multi-organization deployment. Triggers on: 'multi-tenant', 'tenant isolation',
  'SaaS readiness', 'licensing', 'white-label', 'subscription tier', 'per-seat pricing',
  'data isolation', 'RLS', 'cross-tenant', 'onboarding automation', 'usage metering',
  'rate limiting per tenant', 'tenant provisioning', or any reference to scaling the
  platform to multiple paying organizations.
version: 1.0.0
author: TL Development LLC
target: Perennia AI Platform (all layers)
---

# /u-multi-tenant-challenge — SaaS Readiness Validation Engine

Validates that Perennia AI can safely scale to thousands of licensed organizations
with complete data isolation, fair resource allocation, and enterprise-grade
tenant lifecycle management.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                 CHALLENGE RUNNER (CLI / API)                 │
├─────────────────────────────────────────────────────────────┤
│  8 DOMAINS × 87 CHECKS                                     │
│                                                             │
│  1. Tenant Isolation (18 checks)     — Data can NEVER leak │
│  2. Licensing & Subscription (12)    — Billing works right  │
│  3. Provisioning & Lifecycle (10)    — Onboard/offboard     │
│  4. AI Context Isolation (11)        — Agents are scoped    │
│  5. Performance at Scale (10)        — 10k+ tenants hold    │
│  6. White-Label & Branding (8)       — Each org looks theirs│
│  7. Usage Metering & Rate Limits (10)— Fair resource use    │
│  8. Compliance & Audit (8)           — Per-tenant regulatory│
├─────────────────────────────────────────────────────────────┤
│  SCORING: Pass/Fail per check + Domain scores + Overall     │
│  SEVERITY: BLOCKER → CRITICAL → HIGH → MEDIUM               │
│  OUTPUT: JSON results + Markdown report + Remediation plan  │
└─────────────────────────────────────────────────────────────┘
```

## Severity Levels

- **BLOCKER**: Cross-tenant data leak. Ship-stopper. Company-ending risk.
- **CRITICAL**: Security gap that could be exploited. Must fix before licensing.
- **HIGH**: Functional gap that degrades tenant experience. Fix before GA.
- **MEDIUM**: Polish item. Fix within 30 days of launch.

## Usage

```bash
# Full suite
python u_multi_tenant_challenge.py run-all

# Single domain
python u_multi_tenant_challenge.py run --domain isolation
python u_multi_tenant_challenge.py run --domain licensing
python u_multi_tenant_challenge.py run --domain provisioning
python u_multi_tenant_challenge.py run --domain ai_isolation
python u_multi_tenant_challenge.py run --domain performance
python u_multi_tenant_challenge.py run --domain whitelabel
python u_multi_tenant_challenge.py run --domain metering
python u_multi_tenant_challenge.py run --domain compliance

# Reports
python u_multi_tenant_challenge.py report
python u_multi_tenant_challenge.py remediation
```

For full challenge specifications, see IMPLEMENTATION.md
