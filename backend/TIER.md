# Feature Tier System

Perennia AI uses a three-tier system to manage feature surface area and set clear
maintenance expectations. Each backend module is assigned to exactly one tier.

Configuration: `backend/feature_tiers.py`
Gate middleware: `backend/middleware/feature_gate.py`

---

## Tiers

### CORE -- Always Maintained, SLA'd

Core modules are the critical path of the product. They receive:
- Full test coverage requirements
- Bug fixes within 24 hours for P0/P1
- Proactive monitoring and alerting
- Code review required for all changes
- Backward-compatible API guarantees

| Module | Description |
|---|---|
| `leads` | Lead management, CRUD, search, scoring |
| `loans` | Loan pipeline, detail views, stage management |
| `pipeline` | Pipeline analytics, velocity, bottleneck analysis |
| `dashboard` | Main dashboard, KPIs, summary views |
| `tasks` | Task management, assignments, due dates |
| `calendar` | Calendar sync, appointment scheduling |
| `smart_docs` | Document management, needs lists, e-sign |
| `compliance` | Compliance alerts, TRID/RESPA checks, audit |
| `workflow_sla` | SLA tracking, workflow automation, task generation |
| `ai_agents` | AI agent framework, tool registry, orchestration |
| `ai_chat` | AI chat interface, prompt construction, sessions |
| `auth` | Authentication, JWT tokens, RBAC |
| `permissions` | Role-based permissions, page access control |
| `onboarding` | User onboarding, wizard, setup flows |
| `notifications` | Push notifications, email notifications, alerts |
| `portals` | Borrower portal, realtor portal, partner portal |
| `accounting` | Subscription & license management, billing, AP/AR |
| `telephony` | Click-to-call, Telnyx/Twilio integration |
| `dialer` | Power dialer sessions, call queues |
| `content_marketing` | Brand voice, content calendar, publishing |
| `email_intelligence` | Email import, AI categorization, reconciliation |
| `video_clips` | Video clip library, recording management |
| `voicemail_drops` | Ringless voicemail via Slybroadcast |
| `sms_intelligence` | SMS import, conversation intelligence |
| `call_intelligence` | Call recording analysis, coaching insights |
| `referral_partners` | Referral partner management, tracking |
| `rate_monitor` | Rate monitoring, lock advisory |
| `recruiting` | Recruiting engine, candidate management |

### PREMIUM -- Maintained When Resources Allow

Premium modules provide significant value but are not on the critical path.
They receive:
- Bug fixes on a best-effort basis (target: 1 week for P1)
- Feature requests prioritized quarterly
- Monitoring for errors but no SLA on uptime
- Changes reviewed but may be batched

| Module | Description |
|---|---|
| `microsite_builder` | LO microsite pages, theme marketplace |
| `video_meetings` | UVIP video meeting rooms and recording |
| `avatar_studio` | AI avatar generation |
| `hr_management` | HR/people management, skills, goals, OKRs |

#### Deferred (parked until platform is stable)

| Module | Description |
|---|---|
| `salesforce_sync` | Salesforce bidirectional sync |
| `encompass_sync` | Encompass LOS integration |

### EXPERIMENTAL -- Frozen, No SLA

Experimental modules are prototypes, low-usage features, or modules under
evaluation. They receive:
- No active development unless explicitly prioritized
- No bug fix SLA (issues tracked but not scheduled)
- No monitoring beyond basic error logging
- May be deprecated or removed with notice

| Module | Description |
|---|---|
| `decision_lab` | Borrower confidence assessment tool |
| `circle_of_cashflow` | Referral ecosystem questionnaires |

---

## Promotion and Demotion Criteria

### Promoting from EXPERIMENTAL to PREMIUM
A module should be promoted when:
- It has at least 10 active users per week (measured over 4 weeks)
- A product owner commits to maintaining it
- Basic test coverage exists (at least happy-path integration tests)
- It has been reviewed for security and data isolation

### Promoting from PREMIUM to CORE
A module should be promoted when:
- It is used by >50% of active organizations
- Downtime directly impacts revenue or user retention
- It has comprehensive test coverage (unit + integration)
- It has monitoring dashboards and alerting in place
- An on-call rotation covers it

### Demoting from CORE to PREMIUM
A module should be demoted when:
- Usage drops below 30% of active organizations for 2+ months
- It is no longer on the critical revenue path
- Team consensus agrees it can tolerate slower fix times

### Demoting from PREMIUM to EXPERIMENTAL
A module should be demoted when:
- Usage drops below 5 active users per week for 4+ weeks
- The maintaining developer leaves and no one picks it up
- A strategic decision is made to sunset the feature

### Removing an EXPERIMENTAL module
A module should be removed when:
- It has zero usage for 3+ months
- It creates maintenance burden (e.g., blocking dependency upgrades)
- 30 days notice is given to any remaining users

---

## How to Annotate a Module

Each route file should include a comment block after imports indicating its tier:

```python
# ============================================================================
# FEATURE TIER: EXPERIMENTAL
# This module is in the experimental tier -- frozen, no SLA.
# See backend/feature_tiers.py for tier definitions.
# ============================================================================
```

The canonical tier assignment lives in `backend/feature_tiers.py`. The
comment blocks in route files are for developer awareness only -- the source
of truth is the configuration file.

---

## Feature Gate (Optional Enforcement)

The `require_feature_tier` decorator in `backend/middleware/feature_gate.py`
can be applied to individual endpoints to enforce tier-based access control
at the organization level. This is opt-in and not currently applied to any
routes. To use it:

```python
from middleware.feature_gate import require_feature_tier

@router.get("/some-premium-endpoint")
@require_feature_tier("telephony")
async def my_endpoint(request: Request, ...):
    ...
```

This checks `request.state.organization.feature_tier` against the required
tier and returns a 403 if the organization's subscription level is insufficient.
