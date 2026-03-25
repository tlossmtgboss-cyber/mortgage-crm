# Autonomous Morning Pipeline Briefing Agent

## Overview

A scheduled autonomous agent that generates personalized, role-aware morning briefings for every active user before they open the app. Each briefing contains an AI-narrated priorities section plus structured data, tailored to the user's level in the organizational hierarchy:

- **Individual contributors** (LOs, processors) get their personal pipeline and action items.
- **Managers** get their own work plus a subordinate roll-up showing team health, at-risk loans, and who needs attention.
- **Leadership** gets an org-wide briefing with branch comparisons, top risks, and velocity trends.

This is the first autonomous agent loop in the platform — the system acts on behalf of users without being asked.

## Organizational Hierarchy

### New column on `users` table: `manager_id`

| Column | Type | Default | Notes |
|--------|------|---------|-------|
| manager_id | Integer FK (self-referential) | NULL | References `users.id`. NULL = no manager (top of chain). |

**Relationship on User model:**
```python
manager_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
manager = relationship("User", remote_side=[id], foreign_keys=[manager_id], backref="direct_reports")
```

This enables:
- `user.manager` — get this user's manager
- `user.direct_reports` — get all users who report to this user
- Walking the tree at any depth for roll-up briefings

### Briefing Levels

The system determines briefing level from `permission_role` + whether the user has `direct_reports`:

| Level | Condition | Briefing Content |
|-------|-----------|-----------------|
| **Individual** | No direct reports | Personal pipeline, leads, appointments, conditions |
| **Manager** | Has direct reports AND `permission_role` in (management, branch_manager, regional_manager) | Personal work + subordinate roll-up |
| **Leadership** | `permission_role` in (leadership, admin, site_admin) | Personal work (if any) + org-wide roll-up with branch breakdown |

A user always receives their personal section first. Manager and leadership sections are additive — they don't replace the personal briefing.

### Hierarchy Traversal

For **manager briefings**, the query is simple: `SELECT * FROM users WHERE manager_id = :user_id AND is_active = True`. Only direct reports — no recursive tree walking needed.

For **leadership briefings**, the query is org-wide: all active users in the organization, grouped by branch. No manager_id traversal — leadership sees everything.

## Data Model

### New table: `morning_briefings`

| Column | Type | Notes |
|--------|------|-------|
| id | Integer PK | Auto-increment |
| organization_id | Integer FK | Tenant isolation |
| user_id | Integer FK | The recipient |
| briefing_date | Date | One per user per day (in user's local timezone) |
| briefing_level | String | individual, manager, leadership |
| status | String | pending, generating, delivered, failed |
| briefing_data | JSONB | Personal pipeline numbers (6 query results) |
| team_data | JSONB | Nullable. Subordinate/org roll-up data (manager/leadership only) |
| ai_narrative | Text | Priorities paragraph from Haiku |
| html_content | Text | Rendered email HTML, cached |
| email_sent_at | Timestamp | Nullable, set on send |
| email_message_id | String | Nullable, provider message ID |
| viewed_in_app_at | Timestamp | Nullable, set on first in-app view |
| created_at | Timestamp | Default now() |
| updated_at | Timestamp | Default now(), updated on every status change |

**Unique constraint:** `(user_id, briefing_date)` — one briefing per user per day.

**Indexes:**
- `(user_id, briefing_date)` — unique constraint provides this
- `(briefing_date, status)` — for monitoring queries
- `(organization_id, briefing_date)` — for org-level reporting

### New columns on `users` table

| Column | Type | Default | Notes |
|--------|------|---------|-------|
| manager_id | Integer FK | NULL | Self-referential to `users.id` |
| briefing_enabled | Boolean | True | Auto-enrolled, opt-out |
| briefing_hour | Integer | 7 | 0-23 in user's timezone |

### Model Registration

New models must be:
1. `MorningBriefing` imported in `backend/database/models/__init__.py` (required for `configure_mappers()`)
2. Re-exported so `from database.models import MorningBriefing` works
3. `manager_id` column and relationship added to existing User model in `backend/database/models/core.py`

### Data Retention

Briefings older than 90 days are deleted by a weekly cleanup task:

```python
"morning-briefing-cleanup": {
    "task": "tasks.morning_briefing_tasks.cleanup_old_briefings",
    "schedule": crontab(hour="3", minute="0", day_of_week="sunday"),
    "options": {"queue": "default"},
}
```

Deletes rows where `briefing_date < today - 90 days`.

## Scheduling

### Celery Beat Configuration

A single Beat task runs every 15 minutes:

```python
"morning-briefing-dispatch": {
    "task": "tasks.morning_briefing_tasks.dispatch_briefings",
    "schedule": crontab(minute="0,15,30,45"),
    "options": {"queue": "ai_tasks"},
}
```

### Celery Task Discovery

Add `"tasks.morning_briefing_tasks"` to the `include` list in `backend/tasks/celery_app.py` so Celery discovers the tasks.

Add routing rule: `"tasks.morning_briefing_tasks.*": {"queue": "ai_tasks"}`.

### Dispatch Logic

Each 15-minute run:

1. Get current UTC time.
2. Query all active users where `briefing_enabled = True` (no RLS context in Celery tasks — query uses explicit `users.is_active = True` filter).
3. For each user, convert UTC to their `users.timezone` using `zoneinfo`.
4. Compute `local_date = now_in_user_tz.date()`.
5. Determine briefing level based on `permission_role` + whether the user has direct reports.
6. If local hour matches `briefing_hour` AND no `morning_briefings` row exists for `(user_id, local_date)` → enqueue `generate_user_briefing(user_id, local_date_str, briefing_level)`.
7. The DB check before enqueuing prevents queueing the same task 4 times within the same hour. The unique constraint is a secondary safety net.

### Ordering: Individual Briefings Before Manager Briefings

Manager briefings reference subordinate data. To avoid querying loan data twice, **individual briefings are enqueued first** (countdown=0), and **manager/leadership briefings are enqueued with a 5-minute delay** (countdown=300). This gives individual briefings time to populate `morning_briefings` rows that manager briefings can optionally reference for subordinate summaries. However, manager briefings do NOT depend on individual briefings existing — they gather data independently via SQL. The delay is an optimization, not a dependency.

### DST Handling

- **Spring forward:** Briefing hours in the 2-3 AM range (effectively unused) may be skipped. No impact on 5-10 AM delivery hours.
- **Fall back:** First occurrence of the repeated hour triggers the briefing. The unique constraint prevents a second send.

### Concurrency Control

- Dispatch enqueues with stagger delay: `countdown=idx * 2` for individuals, `countdown=300 + idx * 2` for managers/leadership.
- Maximum concurrent AI calls: 10 (via `ai_tasks` queue worker concurrency).
- At 2-4 seconds per briefing, 100 users complete in ~20-40 seconds with concurrency 10.

### Individual Briefing Task

```python
@celery_app.task(
    name="tasks.morning_briefing_tasks.generate_user_briefing",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
    queue="ai_tasks",
)
def generate_user_briefing(self, user_id: int, briefing_date_str: str, briefing_level: str):
    ...
```

## Data Gathering

### Level 1: Individual (same for all users)

Six parameterized SQL queries, all with explicit `organization_id` in the WHERE clause (no RLS in Celery context).

**Column mapping per table:**
- `loans` → `loan_officer_id`, `organization_id`
- `leads` → `owner_id`, `organization_id`
- `scheduler_appointments` → `assigned_user_id`, `organization_id`
- `compliance_alerts` → join via `compliance_alerts.loan_id → loans.id` where `loans.loan_officer_id = :user_id`

**Queries:**

1. **Pipeline Snapshot** — Active loans count, volume, stage breakdown, closing in 7 days.
2. **At-Risk Loans** — SLA breaches, lock expirations in 3 days, stagnant 10+ days.
3. **Stale Leads** — `leads.owner_id = :user_id`, `last_contact` > 7 days. Hot leads (score >= 70) going cold (> 3 days).
4. **Today's Appointments** — `scheduler_appointments.assigned_user_id = :user_id`, `scheduled_start` within today in user's timezone. Fields: `attendee_name`, type, `scheduled_start`.
5. **Pending Conditions** — Open `compliance_alerts` on this user's loans. Past-due conditions.
6. **Yesterday's Activity** — Funded loans, new pipeline additions, lead conversions.

**Target:** < 500ms total per user.

Results stored in `morning_briefings.briefing_data` JSONB.

### Level 2: Manager (additional queries)

Four additional queries for the subordinate roll-up. Scoped to direct reports: `users.manager_id = :user_id AND users.is_active = True`.

7. **Team Pipeline Summary** — For each direct report: name, active loan count, total volume, avg days in stage, number at-risk. One row per subordinate.

8. **Team At-Risk Roll-Up** — All loans across direct reports that exceed SLA targets or have expiring locks. Grouped by subordinate name. This answers: "Which of my people have problems?"

9. **Team Lead Health** — For each direct report: total lead count, leads with `last_contact` > 7 days, hot leads going cold. Identifies which subordinates are neglecting their leads.

10. **Team Activity Summary** — Per subordinate: loans funded this week, appointments today, tasks overdue. High-level scoreboard.

**Implementation:** These queries use `loans.loan_officer_id IN (SELECT id FROM users WHERE manager_id = :user_id)` — a single subquery, not N+1. Same pattern for leads via `leads.owner_id IN (...)`.

**Target:** < 800ms total (individual queries + team queries).

Results stored in `morning_briefings.team_data` JSONB.

### Level 3: Leadership (additional queries)

Four additional queries for the org-wide roll-up. Scoped to entire organization.

11. **Org Pipeline Snapshot** — Org-wide active loans, total volume, velocity (funded last 30 days), stage breakdown.

12. **Branch Comparison** — For each branch: active loan count, volume, avg days in stage, at-risk count, funded this month. Sorted by volume descending. Answers: "Which branches are performing?"

13. **Org Top Risks** — Top 10 at-risk loans across the entire org (worst SLA breaches, nearest lock expirations). Includes LO name and branch.

14. **Org Activity Trends** — Funded count this week vs last week, new pipeline this week vs last week, lead conversion rate trend. Directional arrows (up/down).

**Implementation:** Queries filter on `loans.organization_id = :org_id` (no LO filter). Branch comparison groups by `users.branch_id` joined to `branches.name`.

**Target:** < 1 second total (individual + org queries).

Results stored in `morning_briefings.team_data` JSONB (same column, different structure based on `briefing_level`).

## AI Narrative Generation

### Model

`claude-haiku-4-5-20251001` — fast, cheap, sufficient for structured prioritization.

### Level-Specific System Prompts

**Individual:**
```
You are a senior mortgage pipeline advisor. Given the loan officer's
current pipeline data, write exactly 3 prioritized actions for today.
Each priority should name a specific loan/lead, explain WHY it's urgent,
and state the ONE action to take. Be direct — no pleasantries, no hedging.
Write in second person ("You should..."). Keep total response under 200 words.
```

**Manager:**
```
You are a senior mortgage operations advisor. Given a manager's personal
pipeline and their team's performance data, write exactly 3 priorities.
Priority 1 should address the most urgent team issue (a subordinate with
at-risk loans or neglected leads). Priorities 2-3 can be personal pipeline
items or team items — pick whichever is most urgent. Name specific people
and loans. Write in second person. Keep total response under 250 words.
```

**Leadership:**
```
You are a chief strategy advisor for a mortgage lending operation. Given
the organization's pipeline data and branch performance, write exactly 3
strategic priorities. Focus on trends, branch performance gaps, and
org-wide risks. Name specific branches and top-risk loans. Do not drill
into individual LO performance — that's for their managers. Write in
second person. Keep total response under 250 words.
```

### Parameters

- Max tokens: 350 (slightly higher for manager/leadership narratives)
- Temperature: 0.3
- Sync Anthropic client (no async needed in Celery)

### Graceful Degradation

If the API call fails, the briefing sends with data sections only and a note: "AI priorities unavailable today — here's your data."

## Email Template

### Structure by Level

**All levels share:**
```
Subject line format:
  Individual: "Your Morning Briefing — [date] — 3 priorities, N active loans"
  Manager:    "Team Briefing — [date] — 3 priorities, N team members"
  Leadership: "Org Briefing — [date] — 3 priorities, $NM pipeline"

Body header:
  "Good morning, [First Name]"
  TOP 3 PRIORITIES — AI narrative
  ─────────────────
```

**Individual sections:**
```
  PIPELINE SNAPSHOT — count, volume, stage table
  AT-RISK — loans exceeding SLA / expiring locks
  LEADS GOING COLD — high-score leads with no contact
  TODAY'S APPOINTMENTS — time, attendee, type
```

**Manager sections (appended after personal sections):**
```
  ─────────────────
  YOUR TEAM
  ┌──────────────┬───────┬──────────┬─────────┐
  │ Name         │ Loans │ Volume   │ Health  │
  ├──────────────┼───────┼──────────┼─────────┤
  │ Jane Smith   │  8    │ $2.1M    │ 🟢      │
  │ Mike Jones   │  5    │ $1.4M    │ 🟡 2 at-risk │
  │ Sara Lee     │  3    │ $890K    │ 🔴 SLA breach │
  └──────────────┴───────┴──────────┴─────────┘

  TEAM ATTENTION NEEDED
  · Mike Jones — Johnson loan lock expires tomorrow
  · Sara Lee — 3 leads with no contact in 10+ days
```

**Leadership sections (appended after personal sections, if any):**
```
  ─────────────────
  ORGANIZATION OVERVIEW
  $42M pipeline · 127 active loans · 12 funded this week (↑ vs 9 last week)

  BRANCH PERFORMANCE
  ┌──────────────┬───────┬──────────┬─────────┐
  │ Branch       │ Loans │ Volume   │ Health  │
  ├──────────────┼───────┼──────────┼─────────┤
  │ Main St.     │  45   │ $18M     │ 🟢      │
  │ Downtown     │  38   │ $14M     │ 🟡      │
  │ Westside     │  22   │ $6M      │ 🔴      │
  └──────────────┴───────┴──────────┴─────────┘

  TOP RISKS (org-wide)
  · Johnson file (Main St., LO: Jane Smith) — lock expires tomorrow
  · Davis file (Westside, LO: Sara Lee) — 15 days in UW, SLA target: 5
```

### Health Indicator Logic

- 🟢 Green: no at-risk loans, no stale leads, avg days in stage < SLA target
- 🟡 Yellow: 1-2 at-risk loans OR some stale leads
- 🔴 Red: 3+ at-risk loans OR SLA breach OR lock expiring today

### Email Classification

Internal product emails to authenticated employees, not marketing. CAN-SPAM does not apply. Footer includes: "Adjust or disable morning briefings in Settings."

### Sending

Via sync `NotificationService` (SendGrid). The `from_email` defaults to `briefing@perenniaai.com`.

Rendered HTML cached in `morning_briefings.html_content`.

## In-App Delivery

### Dashboard Component: `MorningBriefingCard`

Positioned at the top of the Dashboard, above existing content. On page load:

1. Calls `GET /api/v1/briefing/today`.
2. Response states:
   - `200` with `status: "delivered"` → render card with level-appropriate sections.
   - `200` with `status: "generating"` → skeleton: "Your morning briefing is being prepared..."
   - `200` with `status: "failed"` → show nothing (silent).
   - `204` → no briefing yet → show nothing.
3. Auto-fires `POST /api/v1/briefing/{id}/viewed` on first render.

The card is:
- Collapsible with sections (personal data collapsed by default for managers, team section expanded).
- Dismissible for the day (localStorage).
- Interactive: loan/lead/user names are clickable links.
- Level-aware: individual users see personal sections only; managers see team table; leadership sees branch table.

### Error State

If `GET /api/v1/briefing/today` fails, the card is not shown. Briefings are supplementary, not critical path.

## API Endpoints

All endpoints require authentication via `get_current_user`. Scoped to `current_user`.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/briefing/today` | Get current user's briefing for today |
| GET | `/api/v1/briefing/history?page=1&per_page=10` | Paginated history, default 30 days |
| POST | `/api/v1/briefing/generate-now?force=false` | Manually trigger briefing |
| POST | `/api/v1/briefing/{id}/viewed` | Mark briefing as viewed in-app |
| GET | `/api/v1/briefing/preferences` | Get briefing_enabled, briefing_hour |
| PUT | `/api/v1/briefing/preferences` | Update briefing_enabled, briefing_hour |

### `GET /api/v1/briefing/today`

Pure read, no side effects. Returns `200` or `204`.

**Response schema (200):**
```json
{
  "id": 1234,
  "briefing_date": "2026-03-24",
  "briefing_level": "manager",
  "status": "delivered",
  "ai_narrative": "1. Check in with Sara Lee...",
  "pipeline": { "active_count": 12, "total_volume": 4200000, "by_stage": {} },
  "at_risk": [ { "loan_number": "...", "borrower": "...", "reason": "..." } ],
  "stale_leads": [ { "name": "...", "score": 82, "days_silent": 5 } ],
  "appointments": [ { "time": "10:00 AM", "attendee": "...", "type": "..." } ],
  "conditions": [ { "title": "...", "severity": "...", "loan_number": "..." } ],
  "yesterday": { "funded": 1, "new_loans": 2, "conversions": 0 },
  "team": {
    "members": [
      { "name": "Jane Smith", "loan_count": 8, "volume": 2100000, "health": "green", "at_risk_count": 0 },
      { "name": "Mike Jones", "loan_count": 5, "volume": 1400000, "health": "yellow", "at_risk_count": 2 }
    ],
    "attention_items": [
      { "user_name": "Mike Jones", "issue": "Johnson loan lock expires tomorrow", "severity": "high" }
    ]
  },
  "viewed_in_app": false,
  "created_at": "2026-03-24T11:00:00Z"
}
```

The `team` field is null for individual-level briefings. For leadership, `team` contains `branches` array instead of `members`.

### `POST /api/v1/briefing/generate-now?force=false`

Enqueues `generate_user_briefing(user_id, today_str, level)`. Returns `202`. With `force=true`, deletes existing briefing and regenerates. Without `force`, returns `409` if exists.

### `POST /api/v1/briefing/{id}/viewed`

Sets `viewed_in_app_at = now()` if not already set. Returns `200`.

### `PUT /api/v1/briefing/preferences`

```json
{ "briefing_enabled": true, "briefing_hour": 7 }
```

Validates `briefing_hour` 0-23.

## Settings UI

In Settings page, "Morning Briefing" section:

```
Morning Briefing
  [x] Enable daily briefing
  Delivery time: [ 7:00 AM v ]
  (in your timezone: America/New_York)
  [ Generate Now ]
```

No level-selection UI — the level is determined automatically from the user's role and direct reports.

## Migration

Single migration script: `backend/migrations/add_morning_briefings.py`

1. Add `manager_id` (Integer FK, nullable) to `users` with index.
2. Add `briefing_enabled` (Boolean, default True) to `users`.
3. Add `briefing_hour` (Integer, default 7) to `users`.
4. Create `morning_briefings` table with all columns and indexes.
5. Uses `ALTER TABLE ADD COLUMN IF NOT EXISTS` pattern.
6. Runs at startup via existing migration pattern.

Note: `manager_id` will be NULL for all existing users. Admins populate it via a future org-chart UI or bulk import. Until populated, all users receive individual-level briefings (the system checks `direct_reports` count, which is 0 when no one has `manager_id` pointing to them).

## File Structure

```
backend/
  database/models/morning_briefing.py    — MorningBriefing SQLAlchemy model
  database/models/core.py                — Add manager_id + relationship to User
  database/models/__init__.py            — Add import + re-export of MorningBriefing
  tasks/morning_briefing_tasks.py        — Celery tasks (dispatch + generate + cleanup)
  tasks/celery_app.py                    — Add to include list + beat_schedule + routing
  services/morning_briefing_service.py   — Data gathering, level detection, AI call, rendering
  routes/briefing_routes.py              — API endpoints
  migrations/add_morning_briefings.py    — DB migration
  templates/morning_briefing_email.py    — HTML email template builder (level-aware)

frontend/
  src/components/dashboard/MorningBriefingCard.js   — Dashboard card (level-aware)
  src/components/dashboard/MorningBriefingCard.css   — Card styles
```

## Error Handling

| Failure | Behavior |
|---------|----------|
| DB query fails | Retry task (max 2 retries, 5 min delay) |
| Anthropic API fails | Send data-only briefing without AI narrative |
| Email send fails | Mark status "failed", retry task |
| All retries exhausted | Log error, mark status "failed", do not send |
| Duplicate briefing attempt | DB check prevents enqueuing; unique constraint is safety net |
| User timezone invalid | Default to America/New_York, log warning |
| manager_id cycle (A→B→A) | Not validated at DB level; briefing generation only queries direct reports (1 level deep), never recurses. Cycles are harmless. |
| User has no loans/leads | Briefing still generates with empty sections + AI narrative says "No active pipeline items — great time to prospect." |

## Monitoring

Log these metrics:

- `briefing.dispatch.count` — users enqueued per dispatch run (by level)
- `briefing.generate.duration_ms` — time per briefing (target: < 3s individual, < 5s manager, < 7s leadership)
- `briefing.generate.ai_duration_ms` — Anthropic API latency
- `briefing.generate.success` / `briefing.generate.failure` — counts by level
- `briefing.email.sent` / `briefing.email.failed` — counts
- `briefing.viewed_in_app` — in-app views per day

All logged via `logger.info()` with structured fields.

## Cost Estimate

At scale of 100 users (80 individual, 15 managers, 5 leadership):
- Haiku API: ~$0.12/day ($3.60/month) — managers/leadership use slightly more tokens
- Email (SendGrid): ~100 emails/day, free tier
- DB: individual 6 queries, manager +4 queries, leadership +4 queries = ~700 total (~3s)
- Storage: ~100KB/briefing avg x 100/day x 90 days = ~900MB

## Success Metrics

- **Delivery rate:** % of enabled users who receive briefing by their configured hour
- **Open rate:** % of emails opened (via SendGrid tracking)
- **In-app engagement:** % of briefings viewed in-app (`viewed_in_app_at` not null)
- **Manager engagement:** % of manager briefings where the team section is expanded (tracked via card interaction events)
- **Target:** 95% delivery rate, 60%+ open rate within first month
