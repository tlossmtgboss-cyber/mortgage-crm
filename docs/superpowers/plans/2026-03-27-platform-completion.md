# Perennia AI — Platform Completion Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete all remaining development work to bring Perennia AI from current state (~90% enterprise readiness) to fully production-ready, shippable platform.

**Architecture:** The platform is a FastAPI + React multi-tenant SaaS mortgage CRM with 20+ AI agents, voice workflows, Smart Calendar, and compliance automation. The remaining work falls into 4 priority tiers spanning 8 workstreams.

**Tech Stack:** FastAPI, React 18, PostgreSQL 15 + pgvector, Redis, Celery, LangGraph, Twilio/Telnyx, Vapi

---

## Current State Summary

| Area | Status | What's Done | What Remains |
|------|--------|-------------|--------------|
| Enterprise Security | 95% | API key hashing, RBAC middleware, PII filter, 47 indexes | Load testing validation |
| Voice Scheduling | 70% | Models, service, SMS intercept, conversation service | Tool handler→state machine wiring, reply tracking |
| Morning Briefing | 80% | Backend service + routes + Celery tasks + basic UI | Rich UI (reverted), standalone /briefing page |
| Smart Calendar | 90% | 40+ files, slot engine, conflict detection | Unified entry point, demo data |
| Frontend | 85% | 356 pages, dark mode, mobile responsive | Aria CSS polish, briefing page |
| Compliance | 80% | TRID, ECOA models, HMDA export, retention tasks | 50-state disclosure database |
| White-Label | 60% | WhiteLabelConfig model, email templates | Email briefing branding, domain SSL |
| Monitoring | 50% | DataDog middleware, Sentry in requirements | Verify active, add alerting rules |

---

## Priority 1 — Must Ship (Broken or reverted functionality)

### Task 1: Re-Wire Voice Tool Handler to State Machine

The `start_scheduling_workflow` tool handler (voice/tool_handlers.py:501-581) was reverted to a stateless approach — it sends SMS directly without creating a VoiceWorkflow record. The SMS intercept (telnyx_webhook_routes.py:406+) looks for active workflows but finds none. This makes reply tracking dead.

**Files:**
- Modify: `backend/routes/voice/tool_handlers.py:501-581`
- Reference: `backend/services/voice_scheduling_workflow_service.py`
- Reference: `backend/services/scheduling_conversation_service.py`
- Test: `backend/tests/test_voice_scheduling_workflow_service.py`

- [ ] **Step 1: Write failing test for workflow creation from tool handler**

```python
# tests/test_voice_tool_handler_scheduling.py
def test_start_scheduling_workflow_creates_voice_workflow():
    """Tool handler should create VoiceWorkflow record before sending SMS."""
    # Mock DB, telnyx_send_sms, verify VoiceWorkflow is created
    pass
```

- [ ] **Step 2: Replace stateless SMS in tool handler with state machine flow**

Replace the `start_scheduling_workflow` block (lines 501-581) with:
```python
elif func_name == "start_scheduling_workflow":
    contact_name = args.get("contact_name", "")
    contact_phone = args.get("contact_phone", "")
    meeting_type = args.get("meeting_type", "discovery_call")
    message_context = args.get("message_context", "")

    if not contact_name or not contact_phone:
        return {"success": False, "message": "Contact name and phone number are required."}

    try:
        from services.voice_scheduling_workflow_service import VoiceSchedulingWorkflowService
        from services.scheduling_conversation_service import SchedulingConversationService

        vw_service = VoiceSchedulingWorkflowService(db)
        workflow = vw_service.create_workflow(
            organization_id=organization_id or 0,
            user_id=user_id or 0,
            workflow_type="voice_schedule",
            contact_name=contact_name,
            contact_phone=contact_phone,
            meeting_type=meeting_type,
            message_context=message_context,
        )

        sched_service = SchedulingConversationService(db)
        result = sched_service.initiate_scheduling(
            workflow_id=workflow.id,
            user_id=user_id or 0,
            organization_id=organization_id or 0,
            contact_name=contact_name,
            contact_phone=contact_phone,
            meeting_type=meeting_type,
            message_context=message_context,
        )

        logger.info(
            "Scheduling workflow started via voice tool",
            extra={
                "workflow_id": str(workflow.id),
                "contact_phone": mask_phone(contact_phone),
            },
        )

        return {
            "success": True,
            "workflow_id": workflow.id,
            "message": f"Scheduling workflow started! SMS sent to {contact_name} with available time slots. They can reply to pick a time.",
        }

    except Exception as e:
        logger.error(f"Error starting scheduling workflow: {e}")
        db.rollback()
        return {"success": False, "message": f"Failed to start scheduling workflow: {str(e)}"}
```

- [ ] **Step 3: Verify SchedulingConversationService.initiate_scheduling() works end-to-end**

The method signature is confirmed: `initiate_scheduling(workflow_id, user_id, organization_id, contact_name, contact_phone, meeting_type, duration_minutes, message_context)`. It:
1. Fetches 3 available slots
2. Builds SMS text
3. Send via Telnyx
4. Advance workflow state to `sms_sent` then `awaiting_reply`

- [ ] **Step 4: Run tests**

```bash
cd backend && python -m pytest tests/test_voice_scheduling_workflow_service.py tests/test_voice_tool_handler_scheduling.py -v
```

- [ ] **Step 5: Manual smoke test — trigger voice scheduling and verify workflow record created**

- [ ] **Step 6: Commit**

```bash
git add backend/routes/voice/tool_handlers.py backend/tests/
git commit -m "feat: re-wire voice tool handler to VoiceWorkflow state machine"
```

---

### Task 2: Restore Rich MorningBriefingCard UI

The revert (dc025b33) stripped the MorningBriefingCard from 549→203 lines and CSS from 426→162 lines. The rich version had health indicators, pulsing animations, narrative expansion, and refresh capability.

**Files:**
- Modify: `frontend/src/components/dashboard/MorningBriefingCard.js` (203→~500 lines)
- Modify: `frontend/src/components/dashboard/MorningBriefingCard.css` (162→~400 lines)

> **Shortcut:** Recover the pre-revert rich version via `git show 830b126c:frontend/src/components/dashboard/MorningBriefingCard.js` and adapt from there rather than rewriting from scratch.

- [ ] **Step 1: Restore health indicator system**

Add health scoring to the card — green/yellow/red dots based on briefing data:
- Pipeline health: green if on-track, yellow if at-risk count > 0, red if > 3
- SLA health: based on conditions with past-due deadlines
- Lead health: based on stale lead count

- [ ] **Step 2: Restore narrative expansion/collapse**

The AI narrative should be truncated to 3 lines with "Read more" toggle.

- [ ] **Step 3: Restore refresh button**

Add a refresh icon button that calls `POST /api/v1/briefing/generate-now?force=true`.

- [ ] **Step 4: Restore section collapse with counts**

Each section (Pipeline, At-Risk, Stale Leads, etc.) should be collapsible with a badge showing item count.

- [ ] **Step 5: Restore CSS animations and health colors**

```css
@keyframes pulse-green { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
@keyframes pulse-yellow { 0%, 100% { opacity: 1; } 50% { opacity: 0.6; } }
@keyframes pulse-red { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }

.health-dot--green { background: #22c55e; animation: pulse-green 2s infinite; }
.health-dot--yellow { background: #eab308; animation: pulse-yellow 1.5s infinite; }
.health-dot--red { background: #ef4444; animation: pulse-red 1s infinite; }
```

- [ ] **Step 6: Test in browser — verify card renders on dashboard with all sections**

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/dashboard/MorningBriefingCard.js frontend/src/components/dashboard/MorningBriefingCard.css
git commit -m "feat: restore rich MorningBriefingCard with health indicators and animations"
```

---

### Task 3: Verify utils.py ai_config Fix

> **Note:** This overlaps with Task 1 of `2026-03-25-aria-call-intelligence-integration.md`. If that plan's Task 1 has already been executed, skip this task entirely. This is a quick verification only.

**Files:**
- Check: `backend/routes/voice/utils.py`

- [ ] **Step 1: Verify module imports cleanly**

```bash
cd backend && python -c "from routes.voice.utils import *; print('OK')"
```

- [ ] **Step 2: If import fails, fix the issue. Otherwise mark complete.**

---

## Priority 2 — Should Ship (Missing features that users expect)

### Task 4: Create Standalone /briefing Page

The morning briefing currently only appears as a dashboard card. Enterprise users need a dedicated full-page view with history, preferences, and the current briefing.

**Files:**
- Create: `frontend/src/pages/BriefingPage.js` (~300 lines)
- Create: `frontend/src/pages/BriefingPage.css` (~200 lines)
- Modify: `frontend/src/App.jsx` (add route)

- [ ] **Step 1: Create BriefingPage component**

Three-tab layout:
1. **Today** — Full briefing with all sections expanded (uses `GET /api/v1/briefing/today`)
2. **History** — Paginated list of past briefings (uses `GET /api/v1/briefing/history`)
3. **Preferences** — Inline preferences editor (uses `GET/PUT /api/v1/briefing/preferences`)

- [ ] **Step 2: Create BriefingPage.css**

Match existing dark theme. Use same health indicators as MorningBriefingCard.

- [ ] **Step 3: Add route to App.js**

```jsx
<Route path="/briefing" element={<PrivateRoute><BriefingPage /></PrivateRoute>} />
```

- [ ] **Step 4: Add sidebar navigation link**

Add "Morning Briefing" to `frontend/src/config/roleConfig.js` (drives sidebar nav via `frontend/src/components/Navigation.js`). Add entry with path `/briefing` and appropriate icon for all LO+ roles.

- [ ] **Step 5: Test navigation and data loading**

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/BriefingPage.js frontend/src/pages/BriefingPage.css frontend/src/App.jsx frontend/src/config/roleConfig.js
git commit -m "feat: add standalone /briefing page with today, history, and preferences tabs"
```

---

### Task 5: Demo Data Seeding for Sales Demos

Sales team needs a one-click way to populate a fresh org with realistic demo data — loans at various stages, leads with scores, activities, upcoming appointments, compliance alerts.

**Files:**
- Create: `backend/scripts/seed_demo_org.py` (~400 lines)
- Modify: `backend/routes/admin_ops_routes.py` (add endpoint)

- [ ] **Step 1: Create seed_demo_org.py**

Generates for a given org_id:
- 25 leads (mixed stages, scores, sources)
- 15 loans (spread across pipeline stages, realistic SLA dates)
- 50 activities (calls, emails, meetings over past 30 days)
- 8 upcoming appointments (next 7 days)
- 5 compliance alerts (2 open, 3 resolved)
- 3 documents per active loan
- 1 morning briefing for today

Uses transactions with savepoint per entity type for safe rollback.

- [ ] **Step 2: Add admin endpoint**

```python
@router.post("/api/v1/admin/seed-demo-data")
async def seed_demo_data(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    # Admin-only, creates demo data for current_user's org
```

- [ ] **Step 3: Add cleanup endpoint with tracking table**

Create a `demo_data_records` table (columns: `entity_type`, `entity_id`, `organization_id`, `created_at`) to track seeded records. The seed script inserts tracking rows as it creates entities. The cleanup endpoint deletes by joining against this table — no `is_demo` column needed on existing models.

```python
@router.delete("/api/v1/admin/seed-demo-data")
async def clear_demo_data(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    # Deletes all records tracked in demo_data_records for current org
```

- [ ] **Step 4: Test seeding and cleanup**

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/seed_demo_org.py backend/routes/admin_ops_routes.py
git commit -m "feat: add demo data seeding for sales demos with cleanup"
```

---

### Task 6: Aria CSS Stream C — Polish and Consistency

The Aria CSS files exist and are functional (1,859 total lines across 3 files) but need consistency review and mobile polish.

**Files:**
- Modify: `frontend/src/pages/AriaVoiceApp.css` (1,082 lines)
- Modify: `frontend/src/pages/aria/AriaMortgageCalculator.css` (441 lines)
- Modify: `frontend/src/pages/aria/AriaCalendarPage.css` (336 lines)

- [ ] **Step 1: Audit CSS variable consistency**

Ensure all three files use the same CSS custom property names for theme colors. Check for hardcoded colors that should use variables.

- [ ] **Step 2: Check WCAG touch targets (44px minimum)**

All interactive elements on mobile must meet 44x44px minimum. The MortgageCalculator was already fixed — verify AriaVoiceApp and AriaCalendarPage.

- [ ] **Step 3: Check prefers-reduced-motion**

Ensure all animations respect `@media (prefers-reduced-motion: reduce)`.

- [ ] **Step 4: Check dark/light mode consistency**

Verify no white-on-white or dark-on-dark text in either mode.

- [ ] **Step 5: Test on mobile viewport (375px)**

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/AriaVoiceApp.css frontend/src/pages/aria/
git commit -m "fix: Aria CSS consistency, WCAG compliance, and mobile polish"
```

---

## Priority 3 — Should Have (Value-adds for enterprise positioning)

### Task 7: 50-State Disclosure Database

Currently only 4 states (CA, TX, NY, FL) are hardcoded in `get_state_requirements()`. Enterprise lenders operate across all 50 states.

**Files:**
- Create: `backend/database/models/state_disclosure.py` (~80 lines)
- Create: `backend/database/seed_state_disclosures.py` (~600 lines)
- Modify: `backend/agents/tools/compliance.py` (update `get_state_requirements` to query DB)
- Create: `backend/routes/state_disclosure_routes.py` (~100 lines)

- [ ] **Step 1: Create StateDisclosure model**

```python
class StateDisclosure(Base):
    __tablename__ = "state_disclosures"
    id = Column(Integer, primary_key=True)
    state_code = Column(String(2), nullable=False, index=True)
    category = Column(String, nullable=False)  # licensing, disclosure, fee_limit, prepayment, cooling_off
    requirement = Column(Text, nullable=False)
    applies_to_loan_types = Column(ARRAY(String), nullable=True)  # null = all
    regulatory_reference = Column(String, nullable=True)
    effective_date = Column(Date, nullable=True)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
```

- [ ] **Step 2: Create seed script with all 50 states**

Cover: licensing requirements, state-specific disclosures, fee limits, prepayment rules, cooling-off periods, recording consent laws. Start with the 20 highest-volume states fully populated; remaining 30 as skeleton entries to be completed iteratively with compliance team input.

- [ ] **Step 3: Update get_state_requirements tool to query DB**

Fall back to hardcoded data if table doesn't exist (backward compat).

- [ ] **Step 4: Add admin CRUD routes**

GET /api/v1/admin/state-disclosures?state=CA
PUT /api/v1/admin/state-disclosures/{id}

- [ ] **Step 5: Run seed, verify queries**

- [ ] **Step 6: Commit**

```bash
git add backend/database/models/state_disclosure.py backend/database/seed_state_disclosures.py backend/routes/state_disclosure_routes.py backend/agents/tools/compliance.py
git commit -m "feat: add 50-state disclosure database with seed data"
```

---

### Task 8: White-Label Email Briefings

Morning briefing emails should use the org's white-label branding (logo, colors, company name) instead of default Perennia branding.

**Files:**
- Modify: `backend/tasks/morning_briefing_tasks.py` (email delivery section)
- Modify: `backend/templates/morning_briefing_email.py` (existing template builder — add branding params)
- Reference: `backend/database/models/white_label_config.py`

- [ ] **Step 1: Extend existing `render_briefing_email()` in `morning_briefing_email.py` with branding params**

The existing `render_briefing_email()` function already generates HTML. Add parameters for:
- `{{ company_name }}` / `{{ logo_url }}`
- `{{ primary_color }}` / `{{ secondary_color }}`
- `{{ narrative }}` / `{{ sections }}`
- Uses inline CSS (email client compatibility)

- [ ] **Step 2: Update briefing task to load org branding**

```python
from database.models.white_label_config import WhiteLabelConfig
config = db.query(WhiteLabelConfig).filter_by(organization_id=org_id).first()
branding = {
    "company_name": config.company_name if config else "Perennia AI",
    "logo_url": config.logo_url if config else DEFAULT_LOGO,
    "primary_color": config.primary_color if config else "#1e40af",
}
```

- [ ] **Step 3: Render template with branding and send**

- [ ] **Step 4: Test with and without WhiteLabelConfig**

- [ ] **Step 5: Commit**

```bash
git add backend/tasks/morning_briefing_tasks.py backend/templates/morning_briefing_email.py
git commit -m "feat: white-label email briefings using org branding"
```

---

### Task 9: Production Monitoring Verification

DataDog and Sentry are referenced in the codebase but may not be fully active.

**Files:**
- Check: `backend/datadog_monitoring.py`
- Check: `backend/main.py` (middleware registration)
- Check: `backend/middleware/stack.py`

- [ ] **Step 1: Verify DataDog middleware is registered and DD_API_KEY is set on Railway**

- [ ] **Step 2: Verify Sentry SDK init**

Check if `sentry_sdk.init()` is called in main.py or a startup hook. If not, add it:
```python
import sentry_sdk
sentry_sdk.init(dsn=os.getenv("SENTRY_DSN"), traces_sample_rate=0.1)
```

- [ ] **Step 3: Verify health check endpoints exist**

`GET /health` and `GET /ready` should exist and return status.

- [ ] **Step 4: Document alerting rules needed**

Create `docs/monitoring-runbook.md` with:
- Key metrics to watch (p95 latency, error rate, queue depth)
- Alert thresholds
- Escalation procedures

- [ ] **Step 5: Commit**

```bash
git add backend/main.py docs/monitoring-runbook.md
git commit -m "fix: verify and activate production monitoring (DataDog + Sentry)"
```

---

## Priority 4 — Nice to Have (Future roadmap)

### Task 10: Custom Domain SSL for White-Label Portals

Enterprise clients want `portal.theircompany.com` instead of `app.perenniaai.com`.

**Scope:** This is primarily infrastructure (Vercel/Railway config + Caddy/nginx). Code changes are minimal:
- Add `custom_domain` and `ssl_status` columns to WhiteLabelConfig
- Add domain verification endpoint (DNS TXT record check)
- Add Vercel API integration for custom domain provisioning

**Estimated effort:** 2-3 days (mostly infra)

- [ ] **Step 1: Add `ssl_status` column to WhiteLabelConfig (`custom_domain` already exists)**
- [ ] **Step 2: Add domain verification endpoint**
- [ ] **Step 3: Add Vercel API integration for domain provisioning**
- [ ] **Step 4: Document DNS setup process for clients**

---

### Task 11: Main App White-Labeling

Beyond email and portal, the main React app itself should support per-org branding — logo in sidebar, accent colors, custom favicon.

**Scope:**
- Add `/api/v1/branding` endpoint that returns org's WhiteLabelConfig
- Frontend loads branding on auth and applies CSS custom properties
- Replace hardcoded "Perennia AI" strings with `brandName`

**Estimated effort:** 1-2 days

- [ ] **Step 1: Create branding API endpoint**
- [ ] **Step 2: Create BrandingProvider React context**
- [ ] **Step 3: Apply CSS custom properties from branding config**
- [ ] **Step 4: Replace hardcoded brand strings**

---

### Task 12: Load Testing with New Indexes

47 indexes were added in commit `f058c16e`. Need to validate they actually improve performance under load.

**Scope:**
- Write k6 or locust load test script
- Target key endpoints: pipeline metrics, lead search, loan list, calendar slots
- Measure p95/p99 latency before and after
- Document capacity ceiling

**Estimated effort:** 1 day

- [ ] **Step 1: Write load test script (k6 or locust)**
- [ ] **Step 2: Run against staging with 50/100/200 concurrent users**
- [ ] **Step 3: Document results and identify remaining bottlenecks**

---

## Dependency Graph

```
P1: Task 1 (Voice Wiring) ─────────────────────────── Independent
P1: Task 2 (Rich Briefing Card) ─┐
P2: Task 4 (Briefing Page) ──────┘ Task 4 depends on Task 2
P1: Task 3 (utils.py check) ─────────────────────────── Independent
P2: Task 5 (Demo Data) ──────────────────────────────── Independent
P2: Task 6 (Aria CSS) ───────────────────────────────── Independent
P3: Task 7 (50-State Disclosures) ───────────────────── Independent
P3: Task 8 (WL Email Briefings) ─────────────────────── Independent
P3: Task 9 (Monitoring) ─────────────────────────────── Independent
P4: Task 10 (Custom Domains) ────────────────────────── Depends on Task 11
P4: Task 11 (App White-Label) ───────────────────────── Independent
P4: Task 12 (Load Testing) ──────────────────────────── Independent
```

## Parallelization Strategy

These can be worked in parallel:
- **Stream A (Voice):** Tasks 1, 3
- **Stream B (Briefing):** Tasks 2 → 4, Task 8 (independent)
- **Stream C (Frontend):** Task 6
- **Stream D (Data/Compliance):** Tasks 5, 7
- **Stream E (Infra):** Tasks 9, 12

---

## Summary

| Priority | Tasks | Estimated Total Effort |
|----------|-------|----------------------|
| P1 (Must Ship) | 3 tasks | 1-2 days |
| P2 (Should Ship) | 3 tasks | 2-3 days |
| P3 (Should Have) | 3 tasks | 3-4 days |
| P4 (Nice to Have) | 3 tasks | 4-6 days |
| **Total** | **12 tasks** | **~10-15 days** |

P1 + P2 (6 tasks) gets the platform to a shippable state. P3 adds enterprise polish. P4 is future roadmap.

---

## Related Plans (Not Duplicated Here)

These existing plans cover additional work that is complementary but separate:

| Plan | Scope | Status |
|------|-------|--------|
| `2026-03-24-morning-briefing-agent.md` | Core briefing agent backend (data collection, AI narrative, Celery tasks) | Mostly implemented |
| `2026-03-25-briefing-preferences.md` | Briefing customization (sections, thresholds, tone) | Mostly implemented |
| `2026-03-25-aria-call-intelligence-integration.md` | Voice tool additions (`send_email`, `complete_task`, `send_preapproval`), CI bridge | Not yet started |

The Aria Call Intelligence plan's Tasks 2-8 (new voice tools, CI bridge) are deferred — they add capability but are not required for a shippable platform. Execute them after P2 is complete if voice tool expansion is prioritized.
