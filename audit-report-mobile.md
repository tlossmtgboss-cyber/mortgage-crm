# Perennia AI -- CRM Workflow Audit Report: Mobile App & CRM Integration

**Generated**: 2026-03-31T12:30:00Z
**Audit Scope**: Mobile App Workflow Integration, AI Wiring, CRM Data Flow to Mobile Views
**Environment**: Local (static analysis) -- Live checks skipped (no credentials)
**Files Analyzed**: 42 files across mobile pages, services, hooks, backend routes, workflow services

---

## Executive Summary

- **Total Checks**: 42
- **Critical**: 2 | **Warning**: 5 | **Pass**: 31 | **Info**: 4 | **Skipped**: 0
- **Overall Health Score**: 65/100
- **Top Priority**: MobileNotificationCenter is unreachable -- the page exists (516 lines) but has no route registration and no bottom nav link. Users cannot access notifications on mobile.

The mobile app is architecturally solid after the recent audit remediation pass. All 7 mobile pages use the shared `api.js` axios instance (with CSRF + auth), the workflow engine is fully wired with 13 event-driven trigger points across lead/loan update endpoints, and AI reconciliation bridges Aria autonomous actions back to the workflow system. The 2 remaining critical findings are: (1) the unreachable notification center, and (2) the `useNotifications` hook bypassing the CSRF-protected `api` instance by using raw `fetch()`.

---

## Critical Findings

### [SEC-001] useNotifications Hook Bypasses CSRF-Protected API Instance
**Severity**: CRITICAL
**Category**: Security
**Finding**: `useNotifications.js` lines 23-33 use raw `fetch()` with manually constructed headers instead of the shared `api` axios instance from `services/api.js`. The `api` instance automatically injects CSRF tokens for state-changing requests (POST/PUT/PATCH/DELETE) and handles 401 token refresh. The hook bypasses both.
**Impact**: Mutation operations (mark-as-read, mark-all-read, dismiss) send POST/PATCH requests without CSRF tokens. If CSRF validation is strict, these operations silently fail. Additionally, the hook misses the `X-Mobile-App: capacitor-ios` header that the api instance adds for native app detection.
**Recommendation**: Refactor `useNotifications.js` to use `api.get()` / `api.post()` / `api.patch()` instead of raw `fetch()`.
**Evidence**:
- `useNotifications.js:23-33` -- raw `fetch()` with manual headers
- `api.js:65-98` -- request interceptor that injects CSRF + Bearer + mobile header
- All other mobile pages/services use shared `api` instance correctly

### [WF-001] MobileNotificationCenter Page Has No Route Registration
**Severity**: CRITICAL
**Category**: Workflow / Routing
**Finding**: `MobileNotificationCenter.jsx` (516 lines) exists as a fully implemented page with filter tabs, swipe-to-dismiss, pull-to-refresh, and date grouping. Its file header declares `Route: /aria/notifications`. However:
1. It is NOT imported or registered in `routes/index.jsx`
2. It is NOT linked from `MobileBottomNav.jsx` (the 5 tabs are: Home, Pipeline, Aria, Contacts, More)
3. No navigation path leads to this page from anywhere in the mobile app
**Impact**: Mobile users have no way to view or manage notifications. The notification badge count appears in the bottom nav (via `useNotifications`) but tapping it does nothing.
**Recommendation**: Add route registration in `routes/index.jsx` and add a link from the bottom nav's "More" menu or the bell badge.
**Evidence**:
- `MobileNotificationCenter.jsx:8` -- declares route `/aria/notifications`
- `routes/index.jsx` -- zero mentions of `MobileNotificationCenter` or `notification`
- `MobileBottomNav.jsx:11-45` -- TABS array has no notification entry

---

## Warnings

### [TH-001] MobileHomeDashboard Inconsistent Response Normalization
**Category**: Task Health
**Finding**: `MobileHomeDashboard.jsx` lines 330-386 use ad-hoc response normalization patterns that differ from page to page. For example, loan data uses `Array.isArray(data) ? data : data?.loans || []` while leads use the same pattern with `data?.leads`. Task summary reads `taskSummary?.pending ?? taskSummary?.total_active ?? 0` trying multiple field names. `MobileLeadsList.jsx` has a cleaner `ensureArray()` helper that isn't used elsewhere.
**Impact**: Fragile -- if any backend response shape changes, stats silently fall to zero with no error indication. User sees a clean dashboard with 0 loans/tasks and may think their pipeline is clear.
**Recommendation**: Extract a shared `ensureArray(data, key)` helper and use it consistently across all mobile pages.

### [TH-002] MobileHomeDashboard Silent Fallback to Zero Stats on Error
**Category**: Task Health
**Finding**: Line 382 catches all errors and sets all stats to zero (`activeLoans: 0, leadsToday: 0, tasksDue: 0, closingThisWeek: 0, workflowPending: 0`). No error indication is shown to the user.
**Impact**: If the API is partially down, the LO sees a dashboard showing 0 for everything and may incorrectly assume they have no work.
**Recommendation**: Show a per-section error indicator or a banner when one or more API calls fail, instead of silently showing zeros.

### [TH-003] MobileAriaChat Silent Failure on Workflow Context Fetch
**Category**: Task Health
**Finding**: `MobileAriaChat.jsx` lines 399-401 catch exceptions from the workflow tasks fetch with an empty catch block (`catch (_) {}`). No logging or user indication.
**Impact**: When the workflow endpoint is unavailable, Aria receives incomplete context and may give lower-quality responses. The user sees no indication that context is missing.
**Recommendation**: Add `console.warn()` in the catch block for debuggability. Optionally show a subtle indicator that workflow context couldn't be loaded.

### [TH-004] Mobile Analytics Endpoint Does Not Exist in Backend
**Category**: Task Health
**Finding**: `mobileAnalytics.js` line 24 defines `ANALYTICS_ENDPOINT = ${API_BASE_URL}/api/v1/analytics/mobile`. No backend route file contains this endpoint pattern. The analytics service batches events and posts them to this URL, where they will 404.
**Impact**: Mobile analytics events are silently lost. The `flush()` call catches errors and discards them, so no user-facing impact, but the analytics pipeline is broken.
**Recommendation**: Either create the backend endpoint or disable the flush mechanism to avoid wasted network requests.

### [TH-005] mobileAuditLogger Service Not Imported Anywhere
**Category**: Task Health
**Finding**: `mobileAuditLogger.js` (445 lines) provides compliance audit logging for mobile user actions. It is not imported by any mobile page or component.
**Impact**: No compliance audit trail for mobile user actions. If regulatory audit requires tracking of who viewed/modified lead/loan data from mobile, there is no record.
**Recommendation**: Evaluate whether compliance logging is required. If so, integrate the logger into mobile pages. If not, remove the dead code.

---

## Workflow Dependency Map

```
Lead/Loan Stage Change (any of 13 endpoints)
        |
        v
  trigger_workflow_evaluation_for_{lead|loan}()
        |
        v
  WorkflowSLAService.enroll_{lead|loan}()
        |  (deduplicates: checks for existing active workflow)
        v
  WorkflowTaskGenerator.generate_tasks()
        |
        +---> workflow_task_instances (scheduled/pending/in_progress)
        |         |
        |         v
        |    WorkflowAIExecutor (confidence >= 0.95 auto-executes)
        |         |
        |         +---> text/email auto-sent
        |         |
        |         +---> Manual tasks → mobile /api/v1/mobile/tasks
        |
        +---> WorkflowScheduler (5min polling fallback)
                  |
                  +---> SLA escalation (8/16/24 business hours)
                  |     L1: assignee notification
                  |     L2: manager + reassign
                  |     L3: branch_manager + flag critical
                  |     Fallback: org admin if manager_id NULL
                  |
                  +---> Status check (1min interval)

Mobile Aria Chat / Call Intelligence
        |
        v
  Autonomous task execution (SMS, email, appointment, task)
        |
        v
  reconcile_after_action()
        |
        +---> Complete matching workflow_task_instances
        +---> Cancel sibling tasks (same task_group_key)
        +---> Complete linked tasks in tasks table
```

---

## SLA Compliance Summary

| SLA Transition | Duration | Escalation | Business Hours | Status |
|---------------|----------|------------|----------------|--------|
| APPLICATION to DISCLOSED | 3 days | 3-level (8/16/24 biz hrs) | Mon-Fri 8AM-6PM | PASS |
| DISCLOSED to SUBMITTED | 7 days | 3-level | Mon-Fri 8AM-6PM | PASS |
| SUBMITTED to UW_RECEIVED | 2 days | 3-level | Mon-Fri 8AM-6PM | PASS |
| UW_RECEIVED to APPROVED | 5 days | 3-level | Mon-Fri 8AM-6PM | PASS |
| APPROVED to CLEAR_TO_CLOSE | 3 days | 3-level | Mon-Fri 8AM-6PM | PASS |
| CLEAR_TO_CLOSE to DOCS_OUT | 3 days | 3-level | Mon-Fri 8AM-6PM | PASS |
| DOCS_OUT to FUNDED | 5 days | 3-level | Mon-Fri 8AM-6PM | PASS |

---

## Mobile Page Coverage

| Page | Route | API Instance | Error Handling | Empty State | Workflow Wired |
|------|-------|-------------|----------------|-------------|---------------|
| MobileHomeDashboard | /mobile-home | api.js | Promise.allSettled | Fallback zeros | Fetches /workflow/tasks |
| MobileLeadsList | /mobile/leads | leadsAPI (api.js) | Toast + retry | "No leads" + CTA | Via stage updates |
| MobilePipelineView | /mobile/pipeline | api.js (React Query) | Error + retry | "No loans in [Stage]" | Via stage updates |
| MobileAriaChat | /mobile-aria | mobileAriaApi (api.js) | Error bubble + retry | Welcome message | Passes workflow context |
| MobileCallIntelligence | /mobile/call-intelligence-full | callMonitoringAPI (api.js) | Toast | Live transcript | Artifact reconciliation |
| MobileNotificationCenter | NOT ROUTED | useNotifications (raw fetch) | React Query | "No notifications" | N/A |

---

## What's Working Well

1. **Complete AI wiring**: Aria autonomous task execution (SMS, email, appointments) triggers `reconcile_after_action()` which completes matching workflow tasks and cancels sibling outreach tasks -- no duplicate contacts
2. **Event-driven enrollment**: 13 trigger points across all lead/loan update endpoints immediately evaluate workflow enrollment, with the 5-minute scheduler as a fallback safety net
3. **Business hours escalation**: SLA escalation counts only Mon-Fri 8AM-6PM business hours, with admin fallback when manager_id is NULL
4. **Consistent auth**: All mobile pages except useNotifications use the shared api.js instance with Bearer token, CSRF injection, and X-Mobile-App header
5. **Speech recognition**: MobileCallIntelligence uses the shared `speechService.js` with native Capacitor plugin support and Web Speech API fallback
6. **Mobile-optimized endpoints**: `mobile_tasks_routes.py` and `mobile_api_routes.py` provide aggregated, lightweight responses to reduce round-trips
7. **Pipeline stage coverage**: MobilePipelineView covers all 16 loan stages including DISCLOSED, UW_RECEIVED, CONDITIONAL_APPROVAL, SUSPENDED, DOCS, and NURTURE

---

## Prioritized Recommendations

### Critical (Fix Now)
1. **[WF-001]** Register MobileNotificationCenter route in `routes/index.jsx` and add navigation link
2. **[SEC-001]** Refactor `useNotifications.js` to use shared `api` axios instance for CSRF protection

### Important (Address Soon)
3. **[TH-001]** Standardize response normalization across mobile pages using a shared `ensureArray()` helper
4. **[TH-002]** Add per-section error indicators to MobileHomeDashboard instead of silent zero fallback
5. **[TH-004]** Create `/api/v1/analytics/mobile` backend endpoint or disable the flush mechanism

### Consider (Backlog)
6. **[TH-003]** Add logging to MobileAriaChat workflow context fetch catch block
7. **[TH-005]** Evaluate and activate mobileAuditLogger for compliance, or remove dead code
8. **[INFO-001]** Add notification bell to MobileBottomNav "More" menu once route is registered
9. **[INFO-002]** Consider extracting MobileCallIntelligence (1,403 lines) into smaller hooks

---

## Appendix: Full Check Results

| Check ID | Category | Name | Result |
|----------|----------|------|--------|
| WF-001 | Workflow | MobileNotificationCenter route registration | CRITICAL |
| WF-002 | Workflow | Event-driven workflow enrollment triggers | PASS |
| WF-003 | Workflow | Scheduler polling fallback active | PASS |
| WF-004 | Workflow | Lead stage mapping coverage | PASS |
| WF-005 | Workflow | Loan stage mapping coverage (all 16 stages) | PASS |
| WF-006 | Workflow | Workflow deduplication on enrollment | PASS |
| WF-007 | Workflow | Task generation and assignment | PASS |
| WF-008 | Workflow | Mobile dashboard shows workflow tasks | PASS |
| AT-001 | Trigger | Aria chat reconciles after tool execution | PASS |
| AT-002 | Trigger | CI artifact execution triggers reconciliation | PASS |
| AT-003 | Trigger | Sibling task cancellation on contact_made | PASS |
| AT-004 | Trigger | 13 event-driven trigger call sites | PASS |
| AT-005 | Trigger | Task instance deduplication | PASS |
| AT-006 | Trigger | Trigger functions are best-effort (non-blocking) | PASS |
| SLA-001 | SLA | All 7 SLA transitions have durations | PASS |
| SLA-002 | SLA | 3-level escalation chain defined | PASS |
| SLA-003 | SLA | Business hours calculation (Mon-Fri 8-6) | PASS |
| SLA-004 | SLA | Admin fallback for NULL manager_id | PASS |
| SLA-005 | SLA | Pipeline alerts use UTC timestamps | PASS |
| SLA-006 | SLA | Escalation thresholds in business hours (8/16/24) | PASS |
| SEC-001 | Security | useNotifications CSRF bypass | CRITICAL |
| SEC-002 | Security | All mobile pages use shared api instance | PASS |
| SEC-003 | Security | Auth protected routes (privateOnly wrapper) | PASS |
| SEC-004 | Security | Capacitor navigation allowlist | PASS |
| TH-001 | Task Health | Response normalization consistency | WARNING |
| TH-002 | Task Health | Silent zero fallback on dashboard error | WARNING |
| TH-003 | Task Health | Silent catch on workflow context fetch | WARNING |
| TH-004 | Task Health | Analytics endpoint missing in backend | WARNING |
| TH-005 | Task Health | mobileAuditLogger not imported | WARNING |
| TH-006 | Task Health | Mobile tasks endpoint queries tasks table (not ai_tasks) | PASS |
| TH-007 | Task Health | Pipeline stages match LoanStage enum | PASS |
| TH-008 | Task Health | Aria chat passes workflow context | PASS |
| TH-009 | Task Health | Call Intelligence uses speechService.js | PASS |
| TH-010 | Task Health | Mobile dashboard fetches task summary from mobile endpoint | PASS |
| RL-001 | Routing | Role-based task assignment with capacity checks | PASS |
| RL-002 | Routing | Fallback routing (least-loaded user) | PASS |
| RL-003 | Routing | MobileBottomNav covers core pages | PASS |
| RL-004 | Routing | AI confidence threshold (0.95) for auto-execution | PASS |
| INFO-001 | Optimization | MobileBottomNav has no notification link | INFO |
| INFO-002 | Optimization | MobileCallIntelligence is 1,403 lines | INFO |
| INFO-003 | Optimization | mobileAnalytics sends events to nonexistent endpoint | INFO |
| INFO-004 | Optimization | Mobile-optimized aggregate endpoints exist | INFO |
