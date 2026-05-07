# Dashboard Snapshot in Morning Briefing — Design Spec

**Date:** 2026-05-07
**Status:** Approved

## Summary

Add a full dashboard snapshot to the morning briefing so that opening the briefing replaces the need to visit the dashboard. The snapshot is always included (no toggle), and its scope matches the briefing level: individual sees own data, manager sees branch/team, leadership sees org-wide.

## Architecture: Shared Metrics Service

### New file: `services/dashboard_metrics_service.py`

A shared service that both the dashboard route and the briefing service call. All functions follow the same interface pattern:

```python
def calculate_X(
    db: Session,
    user_id: int,
    org_id: int,
    branch_user_ids: Optional[list] = None,
    lookback_days: int = 30
) -> dict | list:
```

`lookback_days` replaces the `thirty_days_ago` parameter that `calculate_stage_performance()` and `calculate_team_performance()` currently take. Each function computes its own date boundary internally from `lookback_days`.

**Scoping convention:**
- `branch_user_ids = [user_id]` — individual scope
- `branch_user_ids = [id1, id2, ...]` — branch/team scope
- `branch_user_ids = None` — org-wide (leadership)

### Functions to extract from `dashboard_routes.py`

These 4 helpers already exist as standalone functions at module level (lines 44-519). Move them as-is:

| Function | Lines | Returns |
|---|---|---|
| `calculate_stage_performance()` | 44-135 | `list[dict]` — stage name, efficiency %, status |
| `calculate_team_performance()` | 138-243 | `list[dict]` — role name, performance score |
| `calculate_bottlenecks()` | 246-379 | `list[dict]` — issue, stage, affected count, avg delay |
| `calculate_efficiency_trends()` | 382-519 | `dict` — overall/pull-through/time-to-close/behind changes |

### New functions (refactored from inline dashboard route code)

| Function | Source lines | Returns |
|---|---|---|
| `calculate_production_metrics()` | 640-692 | `dict` — annual/monthly/weekly/daily goal vs actual |
| `calculate_pipeline_stats()` | 694-868 | `list[dict]` — stage id, name, count, alerts, volume |
| `calculate_lead_metrics()` | 899-989 | `dict` — new_today, conversion_rate, hot_leads, avg_contact_time, alerts |
| `calculate_profitability()` | 1257-1323 | `dict` — funded_ytd, total_volume, avg_loan_size, gain_on_sale, insights |
| `calculate_loan_issues()` | 1223-1255 | `list[dict]` — top 10 stuck loans with stage, days, SLA, issue |
| `calculate_team_stats()` | 1036-1096 | `dict` — has_team, avg_workload, backlog, sla_missed, insights |
| `calculate_efficiency_summary()` | 1325-1458 | `dict` — overall_score, avg_time_to_close, pull_through_rate, loans_behind, automation_rate |

Each function has its own `try/except` with `db.rollback()` and returns a safe default on failure (matching the briefing service resilience pattern).

### Required imports for shared service

```python
from sqlalchemy.orm import Session
from sqlalchemy import func, extract, case
from database.models import User, Lead, Loan, Task, ReferralPartner, AIColleagueAction
from database.enums import LeadStage, LoanStage
```

## Changes to `dashboard_routes.py`

The route handler becomes a thin orchestrator:

1. Auth + date parsing + scope detection (keep as-is)
2. Cache check (keep as-is)
3. Call shared service functions instead of inline queries
4. Assemble response dict (keep same shape)
5. Cache result (keep as-is)

The response contract does not change — zero frontend dashboard impact. The route drops from ~1540 to ~300 lines.

## Changes to `services/morning_briefing_service.py`

### New method: `_query_dashboard_snapshot()`

```python
def _query_dashboard_snapshot(
    self, db: Session, user_id: int, org_id: int, level: str
) -> dict:
```

**Level-based scoping:**
- `"individual"` — `branch_user_ids = [user_id]`
- `"manager"` — query User table for direct reports + self, pass as `branch_user_ids`
- `"leadership"` — `branch_user_ids = None` (org-wide)

**Calls these shared service functions:**
- `calculate_production_metrics()`
- `calculate_pipeline_stats()`
- `calculate_lead_metrics()`
- `calculate_efficiency_summary()`
- `calculate_profitability()`
- `calculate_loan_issues()`
- `calculate_bottlenecks()`
- `calculate_stage_performance()`
- Manager/leadership only: `calculate_team_stats()`, `calculate_team_performance()`

**Returns:**
```python
{
    "production": { ... },
    "pipeline_stats": [ ... ],
    "lead_metrics": { ... },
    "efficiency": { ... },
    "profitability": { ... },
    "loan_issues": [ ... ],
    "bottlenecks": [ ... ],
    "stage_performance": [ ... ],
    "team_stats": { ... },        # manager/leadership only
    "team_performance": [ ... ],   # manager/leadership only
}
```

### Integration point

In `build_context()` (line 713 of `morning_briefing_service.py`), after the existing individual/manager/leadership data gathering, call `_query_dashboard_snapshot()` and store the result on `ctx.dashboard_snapshot`. The `BriefingContext` dataclass gets a new `dashboard_snapshot: dict` field. When the briefing is persisted, it goes into `briefing_data["dashboard_snapshot"]`.

### Storage

Uses the existing `briefing_data` JSONB column on `MorningBriefing`. No model or migration changes needed.

## AI Narrative Enhancement

The `generate_narrative()` prompt template gets dashboard context appended:

```
Dashboard snapshot:
- Production: {monthly_actual}/{monthly_goal} funded this month ({monthly_progress}%)
- Efficiency score: {overall_score}/100
- Pull-through rate: {pull_through_rate}%
- Avg time to close: {avg_time_to_close} days
- Loans falling behind: {loans_behind}
- Bottlenecks: {bottleneck_count} active
- Profitability: {funded_ytd} funded YTD, ${total_volume:,.0f} volume
```

The AI can then reference metrics naturally in the narrative (e.g., "You're at 12 of 18.5 for the month — on pace if you close 2 more this week.").

## Frontend

### New component: `DashboardSnapshotSection`

Added to `frontend/src/components/briefing/shared.js` alongside the existing shared section components.

**Renders:**
- **Production gauges** — monthly goal vs actual with progress bar, daily/weekly/annual as secondary
- **Pipeline summary** — horizontal bar or compact table of stage counts + volumes
- **Efficiency score** — circular gauge or large number with trend arrow
- **Key metrics row** — pull-through rate, avg time to close, loans behind, automation rate (each with trend arrows)
- **Profitability highlights** — funded YTD, avg loan size, gain on sale
- **Top loan issues** — compact list (max 5 in card, max 10 in full page)
- **Bottlenecks** — compact list with affected count and delay

### Section header

Uses existing `SectionHeader` component with icon and toggle. Always starts open.

### Integration into both views

**`MorningBriefingCard.js`:**
- Add `dashboard_snapshot` to destructured briefing fields
- Render `DashboardSnapshotSection` as the first section after the AI narrative (most important data first)
- Max 5 items for loan issues/bottlenecks (compact card view)

**`BriefingPage.js`:**
- Same placement — after narrative, before pipeline/SLA sections
- Full detail (max 10 items)

### Data source

Reads from `briefing.dashboard_snapshot` which comes from the existing `/api/v1/briefing/today` response (already returns full `briefing_data`). No API route changes needed.

## Briefing level visibility matrix

| Data | Individual | Manager | Leadership |
|---|---|---|---|
| Production metrics | Own | Team aggregate | Org aggregate |
| Pipeline stats | Own loans/leads | Team | Org |
| Lead metrics | Own | Team | Org |
| Efficiency | Own | Team | Org |
| Profitability | Own | Team | Org |
| Loan issues | Own loans | Team loans | Org loans |
| Bottlenecks | Own | Team | Org |
| Stage performance | Own | Team | Org |
| Team stats | -- | Yes | Yes |
| Team performance | -- | Yes | Yes |

## Email Deep-Linking

The briefing email template (`templates/morning_briefing_email.py`) gets a new `_section_dashboard_snapshot()` helper that renders the dashboard data with clickable hyperlinks. Each metric links to the relevant app page with the briefing date as context.

**Link targets:**

| Data | Link URL |
|---|---|
| Production metrics | `{app_url}/dashboard?date={briefing_date}` |
| Pipeline stage counts | `{app_url}/pipeline?stage={stage_id}` |
| Lead metrics | `{app_url}/leads` |
| Efficiency score | `{app_url}/dashboard?date={briefing_date}` |
| Profitability | `{app_url}/dashboard?date={briefing_date}` |
| Individual loan issue | `{app_url}/loans/{loan_id}` |
| Bottleneck (by stage) | `{app_url}/pipeline?stage={stage_id}` |
| Team stats | `{app_url}/team` |

All URLs use `app_url` (defaults to `https://app.perenniaai.com`), matching the existing CTA button and settings link patterns already in the email template.

Values are escaped with `html.escape()` before interpolation (matching existing email template security pattern).

## Testing

- Unit tests for each shared service function (mock db session, verify query filters for each scope)
- Integration test: briefing generation includes `dashboard_snapshot` key in `briefing_data`
- Frontend: verify DashboardSnapshotSection renders for each briefing level
- Regression: dashboard endpoint returns identical response after refactor (compare JSON shape)

## Files changed

| File | Change |
|---|---|
| `services/dashboard_metrics_service.py` | **NEW** — shared metrics functions |
| `routes/dashboard_routes.py` | Refactor to call shared service (same API response) |
| `services/morning_briefing_service.py` | Add `_query_dashboard_snapshot()`, integrate into `build_context()` |
| `frontend/src/components/briefing/shared.js` | Add `DashboardSnapshotSection` |
| `frontend/src/pages/BriefingPage.js` | Render dashboard snapshot section |
| `frontend/src/components/dashboard/MorningBriefingCard.js` | Render dashboard snapshot section |
| `backend/tests/test_dashboard_metrics_service.py` | **NEW** — unit tests for shared service |
| `backend/templates/morning_briefing_email.py` | Add `_section_dashboard_snapshot()` with deep links |
