# Autonomous Morning Pipeline Briefing Agent

## Overview

A scheduled autonomous agent that generates personalized morning briefings for every active loan officer before they open the app. Each briefing contains an AI-narrated "Top 3 Priorities" section plus structured pipeline data, delivered via email and displayed in-app on the Dashboard.

This is the first autonomous agent loop in the platform — the system acts on behalf of the LO without being asked.

## Data Model

### New table: `morning_briefings`

| Column | Type | Notes |
|--------|------|-------|
| id | Integer PK | Auto-increment |
| organization_id | Integer FK | Tenant isolation |
| user_id | Integer FK | The LO |
| briefing_date | Date | One per LO per day (in user's local timezone) |
| status | String | pending, generating, delivered, failed |
| briefing_data | JSONB | Pipeline numbers (6 query results, borrower names included — same PII classification as loans table) |
| ai_narrative | Text | "Top 3 Priorities" paragraph from Haiku |
| html_content | Text | Rendered email HTML, cached |
| email_sent_at | Timestamp | Nullable, set on send |
| email_message_id | String | Nullable, provider message ID |
| viewed_in_app_at | Timestamp | Nullable, set on first in-app view |
| created_at | Timestamp | Default now() |
| updated_at | Timestamp | Default now(), updated on every status change |

**Unique constraint:** `(user_id, briefing_date)` — one briefing per LO per day.

**Indexes:**
- `(user_id, briefing_date)` — unique constraint provides this
- `(briefing_date, status)` — for monitoring queries ("how many failed today?")
- `(organization_id, briefing_date)` — for org-level reporting

### New columns on `users` table

| Column | Type | Default | Notes |
|--------|------|---------|-------|
| briefing_enabled | Boolean | True | Auto-enrolled, opt-out |
| briefing_hour | Integer | 7 | 0-23 in user's timezone |

### Model Registration

The new `MorningBriefing` model must be:
1. Imported in `backend/database/models/__init__.py` (required for `configure_mappers()`)
2. Re-exported so `from database.models import MorningBriefing` works

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
2. Query all active users where `briefing_enabled = True` (no RLS context in Celery tasks — query uses explicit `users.is_active = True` filter, NOT request-scoped RLS).
3. For each user, convert UTC to their `users.timezone` using `pytz` / `zoneinfo`.
4. Compute `local_date = now_in_user_tz.date()` — this is the briefing date for this user.
5. If local hour matches `briefing_hour` AND no `morning_briefings` row exists for `(user_id, local_date)` → enqueue `generate_lo_briefing(user_id, local_date_str)`.
6. The DB check before enqueuing prevents queueing the same task 4 times within the same hour (at :00, :15, :30, :45). The unique constraint is a secondary safety net.

### DST Handling

DST transitions are handled naturally by the timezone conversion:
- **Spring forward:** If 7 AM doesn't exist (clocks jump 2 AM → 3 AM), `briefing_hour = 2` would never match. This only affects LOs with `briefing_hour` in the 2-3 AM range (effectively none — delivery hours are 5-10 AM).
- **Fall back:** If 1 AM occurs twice, the first occurrence triggers the briefing. The unique constraint prevents a second send during the repeated hour.

### Concurrency Control

For large organizations (100+ LOs with the same `briefing_hour`):

- Dispatch enqueues individual tasks with a **stagger delay**: `generate_lo_briefing.apply_async(args=[user_id, date_str], countdown=idx * 2)` where `idx` is the user's position in the batch. This spreads 100 LOs over ~200 seconds instead of a burst.
- Maximum concurrent AI calls: capped at **10** via a Celery worker `--concurrency=10` on the `ai_tasks` queue (or a Redis semaphore if shared workers are used).
- At 2 seconds per briefing (6 queries + 1 API call), 100 LOs complete in ~20 seconds with concurrency 10.

### Individual Briefing Task

```python
@celery_app.task(
    name="tasks.morning_briefing_tasks.generate_lo_briefing",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
    queue="ai_tasks",
)
def generate_lo_briefing(self, user_id: int, briefing_date_str: str):
    ...
```

The task receives `briefing_date_str` (ISO format) from the dispatcher, not computed internally. This ensures the date is consistent with the dispatch decision.

## Data Gathering

Six parameterized SQL queries per LO. Each query explicitly includes `organization_id` in the WHERE clause (no RLS in Celery context).

**Column mapping per table:**
- `loans` → `loan_officer_id`, `organization_id`
- `leads` → `owner_id`, `organization_id`
- `scheduler_appointments` → `assigned_user_id`, `organization_id`
- `compliance_alerts` → join via `compliance_alerts.loan_id → loans.loan_officer_id`

### 1. Pipeline Snapshot

- Active loans count and total volume (excluding terminal stages: FUNDED, CANCELLED, DENIED, DEAD, WITHDRAWN, DOES_NOT_QUALIFY).
- Breakdown by stage with count per stage.
- Loans with `closing_date` in the next 7 days.
- Scoped: `loans.loan_officer_id = :user_id AND loans.organization_id = :org_id`

### 2. At-Risk Loans

- Loans exceeding SLA targets for their current stage transition (using `SLA_TARGETS` dict).
- Loans with `lock_expiration_date` in next 3 days.
- Loans with `stage_changed_at` older than 10 days.
- Scoped: same as Pipeline Snapshot.

### 3. Stale Leads

- Leads with `leads.owner_id = :user_id` and `last_contact` > 7 days ago.
- Leads with `ai_score >= 70` and `last_contact` > 3 days ago (hot leads going cold).
- Scoped: `leads.owner_id = :user_id AND leads.organization_id = :org_id`

### 4. Today's Appointments

- From `scheduler_appointments` where `scheduled_start` (DateTime, stored as UTC) falls within today in the LO's timezone.
- Fields: `attendee_name`, appointment type, `scheduled_start`.
- Scoped: `scheduler_appointments.assigned_user_id = :user_id AND scheduler_appointments.organization_id = :org_id`

### 5. Pending Conditions

- Open compliance alerts (`compliance_alerts.status = 'open'`) on this LO's loans.
- Past-due conditions (`deadline_date < today`).
- Scoped: join `compliance_alerts.loan_id → loans.id` where `loans.loan_officer_id = :user_id AND loans.organization_id = :org_id`

### 6. Yesterday's Activity

- Loans funded yesterday (wins to celebrate).
- New loans added to pipeline yesterday.
- Leads converted to applications yesterday.
- Scoped: same as Pipeline Snapshot / Stale Leads.

**Target:** < 500ms total per LO (6 simple indexed queries).

All results are stored in `morning_briefings.briefing_data` as JSONB for reuse by the email template and in-app card.

## AI Narrative Generation

### Model

`claude-haiku-4-5-20251001` — fast, cheap (~$0.001/briefing at ~2,000 input tokens + 300 output tokens), sufficient for structured prioritization over known data.

### System Prompt

```
You are a senior mortgage pipeline advisor. Given the loan officer's
current pipeline data, write exactly 3 prioritized actions for today.
Each priority should name a specific loan/lead, explain WHY it's urgent,
and state the ONE action to take. Be direct — no pleasantries, no hedging.
Write in second person ("You should..."). Keep total response under 200 words.
```

### User Prompt

The serialized `BriefingContext` — all 6 query results formatted as structured text. Raw data, not pre-analyzed. The AI does the reasoning.

### Parameters

- Max tokens: 300
- Temperature: 0.3
- No streaming (batch context)

### Async-in-Sync Bridge

The Anthropic Python client supports synchronous calls via `anthropic.Anthropic()` (not `AsyncAnthropic`). The Celery task uses the sync client directly — no `asyncio.run()` needed.

### Graceful Degradation

If the Anthropic API call fails after retries, the briefing still sends with all data sections intact and a note in place of the narrative: "AI priorities unavailable today — here's your pipeline data." The `morning_briefings` row is saved with `ai_narrative = NULL` and `status = 'delivered'`.

### Guardrails

- Borrower names appear only in the per-request user prompt, never in the system prompt.
- AI narrative is cached in `morning_briefings.ai_narrative` — never regenerated for the same day.
- No tool calls, no function calling — pure text completion.

## Email Delivery

### Template Structure

```
Subject: "Your Morning Briefing — [March 24] — 3 priorities, 12 active loans"

Body:
  1. Greeting: "Good morning, [First Name]"
  2. TOP 3 PRIORITIES — AI narrative (3 numbered items)
  3. Divider
  4. PIPELINE SNAPSHOT — active loans, volume, stage breakdown table
  5. AT-RISK — loans exceeding SLA or with expiring locks
  6. LEADS GOING COLD — high-score leads with no recent contact
  7. TODAY'S APPOINTMENTS — time, attendee, type
  8. Divider
  9. CTA button: "Open Perennia" → deep link to dashboard
```

HTML with inline CSS only (email-client compatible). No external stylesheets, no JavaScript. Responsive for mobile (single-column, 600px max-width).

### Email Classification

These are internal product emails to authenticated employees, not marketing. CAN-SPAM does not apply. However, the opt-out mechanism (briefing_enabled toggle in Settings) serves the same purpose. No List-Unsubscribe header required, but the email footer includes: "You can adjust or disable morning briefings in Settings."

### Sending

Via `EmailDeliveryService` — but since it's an `async` service and Celery tasks are sync, the task uses the simpler sync `NotificationService` (SendGrid via `sendgrid` package) which already exists at `backend/services/notification_service.py`. The `from_email` is configurable per org or defaults to `briefing@perenniaai.com`.

The rendered HTML is cached in `morning_briefings.html_content` so the in-app card can reference it.

## In-App Delivery

### Dashboard Component: `MorningBriefingCard`

Positioned at the top of the Dashboard, above existing content. On page load:

1. Calls `GET /api/v1/briefing/today`.
2. Response states:
   - `200` with `status: "delivered"` → render the card with AI narrative + data sections.
   - `200` with `status: "generating"` → show skeleton/loading state: "Your morning briefing is being prepared..."
   - `200` with `status: "failed"` → show nothing (silent failure).
   - `204` → no briefing exists yet (before briefing hour) → show nothing.
3. Card uses a "Mark viewed" button or auto-fires `POST /api/v1/briefing/{id}/viewed` on first render (see API section).

The card is:
- Collapsible (click to expand/collapse, remembers state in localStorage).
- Dismissible for the day (hides until tomorrow, stored in localStorage).
- Styled consistently with existing Dashboard cards.
- Interactive: loan/lead names are clickable links to their detail pages.

### Data Flow

The card renders from `morning_briefings.briefing_data` (JSONB) and `morning_briefings.ai_narrative` (text), not from the cached HTML. This allows the in-app version to be interactive while the email version uses static HTML.

### Error State

If `GET /api/v1/briefing/today` fails (network error, 500), the card is not shown. No error toast — briefings are supplementary, not critical path.

## API Endpoints

All endpoints require authentication via `get_current_user`. Scoped to `current_user` — no cross-user access. Any authenticated user can access briefing endpoints (not restricted to `role = 'loan_officer'` — processors and managers may also find briefings useful).

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/briefing/today` | Get current user's briefing for today |
| GET | `/api/v1/briefing/history?page=1&per_page=10` | Paginated history, default 30 days |
| POST | `/api/v1/briefing/generate-now` | Manually trigger briefing (enqueues Celery task) |
| POST | `/api/v1/briefing/{id}/viewed` | Mark briefing as viewed in-app |
| GET | `/api/v1/briefing/preferences` | Get briefing_enabled, briefing_hour |
| PUT | `/api/v1/briefing/preferences` | Update briefing_enabled, briefing_hour |

### `GET /api/v1/briefing/today`

Pure read, no side effects. Returns `200` with briefing or `204` if none exists.

**Response schema (200):**
```json
{
  "id": 1234,
  "briefing_date": "2026-03-24",
  "status": "delivered",
  "ai_narrative": "1. You should call...",
  "pipeline": { "active_count": 12, "total_volume": 4200000, "by_stage": {...} },
  "at_risk": [ { "loan_number": "...", "borrower": "...", "reason": "..." } ],
  "stale_leads": [ { "name": "...", "score": 82, "days_silent": 5 } ],
  "appointments": [ { "time": "10:00 AM", "attendee": "...", "type": "..." } ],
  "conditions": [ { "title": "...", "severity": "...", "loan_number": "..." } ],
  "yesterday": { "funded": 1, "new_loans": 2, "conversions": 0 },
  "viewed_in_app": false,
  "created_at": "2026-03-24T11:00:00Z"
}
```

The response unpacks `briefing_data` JSONB into named top-level fields for frontend convenience.

### `POST /api/v1/briefing/{id}/viewed`

Sets `viewed_in_app_at = now()` if not already set. Returns `200`. Separating the view-tracking from the GET keeps the read endpoint idempotent and cacheable.

### `POST /api/v1/briefing/generate-now`

Enqueues `generate_lo_briefing(user_id, today_str)`. Returns `202 Accepted`. If a briefing already exists for today, accepts a `force=true` query parameter to delete the existing briefing and regenerate (for cases where the pipeline changed significantly). Without `force`, returns `409 Conflict` if a briefing exists.

### `GET /api/v1/briefing/history`

**Query parameters:** `page` (default 1), `per_page` (default 10, max 30).

Returns paginated list of briefings ordered by `briefing_date DESC`. Each item includes `briefing_date`, `status`, `ai_narrative` (truncated to 200 chars), `viewed_in_app` boolean.

### `PUT /api/v1/briefing/preferences`

Request body:
```json
{
  "briefing_enabled": true,
  "briefing_hour": 7
}
```

Validates `briefing_hour` is 0-23. Returns updated preferences.

## Settings UI

In the existing Settings page (`frontend/src/pages/Settings.js`), add a "Morning Briefing" section:

```
Morning Briefing
  [x] Enable daily briefing
  Delivery time: [ 7:00 AM v ]
  (in your timezone: America/New_York)
  [ Generate Now ]
```

- Toggle calls `PUT /api/v1/briefing/preferences`.
- Dropdown offers hourly options from 5 AM to 10 AM.
- Timezone is read-only from user profile.
- "Generate Now" calls `POST /api/v1/briefing/generate-now`.

## Migration

Single migration script: `backend/migrations/add_morning_briefings.py`

1. Create `morning_briefings` table with all columns and indexes.
2. Add `briefing_enabled` (Boolean, default True) to `users`.
3. Add `briefing_hour` (Integer, default 7) to `users`.
4. Uses `ALTER TABLE ADD COLUMN IF NOT EXISTS` pattern for safety.
5. Runs at startup via the existing migration registration pattern.

## File Structure

```
backend/
  database/models/morning_briefing.py    — MorningBriefing SQLAlchemy model
  database/models/__init__.py            — Add import + re-export of MorningBriefing
  tasks/morning_briefing_tasks.py        — Celery tasks (dispatch + generate + cleanup)
  tasks/celery_app.py                    — Add to include list + beat_schedule + routing
  services/morning_briefing_service.py   — Data gathering, AI call, email rendering
  routes/briefing_routes.py              — API endpoints
  migrations/add_morning_briefings.py    — DB migration
  templates/morning_briefing_email.py    — HTML email template builder

frontend/
  src/components/dashboard/MorningBriefingCard.js   — Dashboard card component
  src/components/dashboard/MorningBriefingCard.css   — Card styles
```

## Error Handling

| Failure | Behavior |
|---------|----------|
| DB query fails | Retry task (max 2 retries, 5 min delay) |
| Anthropic API fails | Send data-only briefing without AI narrative |
| Email send fails | Mark status "failed", retry task |
| All retries exhausted | Log error, mark status "failed", do not send |
| Duplicate briefing attempt | DB check in dispatch prevents enqueuing; unique constraint is safety net |
| User timezone invalid | Default to America/New_York, log warning |

## Monitoring

Log these metrics for operational visibility:

- `briefing.dispatch.count` — number of LOs enqueued per dispatch run
- `briefing.generate.duration_ms` — time to generate one briefing (target < 3s)
- `briefing.generate.ai_duration_ms` — Anthropic API call latency
- `briefing.generate.success` / `briefing.generate.failure` — counts
- `briefing.email.sent` / `briefing.email.failed` — counts
- `briefing.viewed_in_app` — count of in-app views per day

All logged via `logger.info()` with structured fields for Railway log aggregation.

## Cost Estimate

At scale of 100 LOs:
- Haiku API: ~$0.10/day ($3/month) at ~$0.001/briefing
- Email (SendGrid): ~100 emails/day, well within free tier
- Celery worker: already running for existing tasks
- DB: 6 queries x 100 LOs = 600 queries per morning (~2 seconds total)
- Storage: ~90KB/briefing x 100/day x 90 days retention = ~810MB

## Success Metrics

- **Delivery rate:** % of enabled LOs who receive briefing by their configured hour
- **Open rate:** % of emails opened (via SendGrid tracking)
- **In-app engagement:** % of briefings viewed in-app (`viewed_in_app_at` not null)
- **Target:** 95% delivery rate, 60%+ open rate within first month
