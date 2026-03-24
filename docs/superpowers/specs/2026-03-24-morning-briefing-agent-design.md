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
| briefing_date | Date | One per LO per day |
| status | String | pending, generating, delivered, failed |
| briefing_data | JSONB | Raw pipeline numbers (6 query results) |
| ai_narrative | Text | "Top 3 Priorities" paragraph from Haiku |
| html_content | Text | Rendered email HTML, cached |
| email_sent_at | Timestamp | Nullable, set on send |
| email_message_id | String | Nullable, provider message ID |
| viewed_in_app_at | Timestamp | Nullable, set on first in-app view |
| created_at | Timestamp | Default now() |

**Unique constraint:** `(user_id, briefing_date)` — one briefing per LO per day.

### New columns on `users` table

| Column | Type | Default | Notes |
|--------|------|---------|-------|
| briefing_enabled | Boolean | True | Auto-enrolled, opt-out |
| briefing_hour | Integer | 7 | 0-23 in user's timezone |

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

### Dispatch Logic

Each 15-minute run:

1. Get current UTC time.
2. Query all active users where `briefing_enabled = True`.
3. For each user, convert UTC to their `users.timezone`.
4. If local hour matches `briefing_hour` AND no `morning_briefings` row exists for today in that user's timezone → enqueue `generate_lo_briefing(user_id)`.
5. The unique constraint on `(user_id, briefing_date)` prevents duplicates if a run overlaps.

### Why 15-minute intervals

- One scheduled task instead of 24+ timezone-specific cron jobs.
- Handles half-hour timezones (India UTC+5:30, Newfoundland UTC-3:30).
- Self-healing: if a run fails, the next 15-min window catches missed LOs.
- Maximum delivery delay is 14 minutes past the configured hour.

### Individual Briefing Task

```python
@celery_app.task(
    name="tasks.morning_briefing_tasks.generate_lo_briefing",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
    queue="ai_tasks",
)
def generate_lo_briefing(self, user_id: int):
    ...
```

## Data Gathering

Six parameterized SQL queries per LO, all scoped to `organization_id` + `loan_officer_id`:

### 1. Pipeline Snapshot

- Active loans count and total volume (excluding terminal stages: FUNDED, CANCELLED, DENIED, DEAD, WITHDRAWN, DOES_NOT_QUALIFY).
- Breakdown by stage with count per stage.
- Loans with `closing_date` in the next 7 days.

### 2. At-Risk Loans

- Loans exceeding SLA targets for their current stage transition (using `SLA_TARGETS` dict).
- Loans with `lock_expiration_date` in next 3 days.
- Loans with `stage_changed_at` older than 10 days.

### 3. Stale Leads

- Leads owned by this LO with `last_contact` > 7 days ago.
- Leads with `ai_score >= 70` and `last_contact` > 3 days ago (hot leads going cold).

### 4. Today's Appointments

- From `scheduler_appointments` where `start_time` falls within today in the LO's timezone.
- Fields: borrower name, appointment type, start time.

### 5. Pending Conditions

- Open compliance alerts (`compliance_alerts.status = 'open'`) on this LO's loans.
- Past-due conditions (`deadline_date < today`).

### 6. Yesterday's Activity

- Loans funded yesterday (wins to celebrate).
- New loans added to pipeline yesterday.
- Leads converted to applications yesterday.

**Target:** < 500ms total per LO (6 simple indexed queries on `loan_officer_id` + `organization_id`).

All results are stored in `morning_briefings.briefing_data` as JSONB for reuse by the email template and in-app card.

## AI Narrative Generation

### Model

`claude-haiku-4-5-20251001` — fast, cheap (~$0.002/briefing), sufficient for structured prioritization over known data.

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
  7. TODAY'S APPOINTMENTS — time, borrower, type
  8. Divider
  9. CTA button: "Open Perennia" → deep link to dashboard
```

HTML with inline CSS only (email-client compatible). No external stylesheets, no JavaScript. Responsive for mobile (single-column, 600px max-width).

### Sending

Via `EmailDeliveryService` with provider waterfall (SendGrid → Microsoft Graph → Gmail). The `from_email` is configurable per org or defaults to `briefing@perenniaai.com`.

The rendered HTML is cached in `morning_briefings.html_content` so the in-app card can reuse it without re-rendering.

## In-App Delivery

### Dashboard Component: `MorningBriefingCard`

Positioned at the top of the Dashboard, above existing content. On page load:

1. Calls `GET /api/v1/briefing/today`.
2. If a briefing exists for today → render the card with AI narrative + data sections.
3. If no briefing exists (LO logged in before their briefing hour) → show nothing.
4. First view sets `viewed_in_app_at` timestamp.

The card is:
- Collapsible (click to expand/collapse, remembers state in localStorage).
- Dismissible for the day (hides until tomorrow).
- Styled consistently with existing Dashboard cards.

### Data Flow

The card renders from `morning_briefings.briefing_data` (JSONB) and `morning_briefings.ai_narrative` (text), not from the cached HTML. This allows the in-app version to be interactive (loan names link to loan detail pages) while the email version uses static HTML.

## API Endpoints

All endpoints require authentication. Scoped to `current_user` — no cross-user access.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/briefing/today` | Get current user's briefing for today |
| GET | `/api/v1/briefing/history` | Last 30 days of briefings, paginated |
| POST | `/api/v1/briefing/generate-now` | Manually trigger briefing (enqueues same Celery task) |
| GET | `/api/v1/briefing/preferences` | Get briefing_enabled, briefing_hour |
| PUT | `/api/v1/briefing/preferences` | Update briefing_enabled, briefing_hour |

### `GET /api/v1/briefing/today`

Returns `200` with briefing data or `204` if no briefing exists yet. Sets `viewed_in_app_at` on first call.

### `POST /api/v1/briefing/generate-now`

Enqueues `generate_lo_briefing(user_id)` on the `ai_tasks` queue. Returns `202 Accepted` with a message. Respects the unique constraint — if a briefing already exists for today, returns `409 Conflict`.

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

1. Create `morning_briefings` table with all columns.
2. Add `briefing_enabled` (Boolean, default True) to `users`.
3. Add `briefing_hour` (Integer, default 7) to `users`.
4. Uses `ALTER TABLE ADD COLUMN IF NOT EXISTS` pattern for safety.
5. Runs at startup via the existing migration registration pattern.

## File Structure

```
backend/
  database/models/morning_briefing.py    — MorningBriefing SQLAlchemy model
  tasks/morning_briefing_tasks.py        — Celery tasks (dispatch + generate)
  services/morning_briefing_service.py   — Data gathering, AI call, email rendering
  routes/briefing_routes.py              — API endpoints
  migrations/add_morning_briefings.py    — DB migration
  templates/morning_briefing_email.py    — HTML email template builder

frontend/
  src/components/dashboard/MorningBriefingCard.js   — Dashboard card
  src/components/dashboard/MorningBriefingCard.css   — Card styles
```

## Error Handling

| Failure | Behavior |
|---------|----------|
| DB query fails | Retry task (max 2 retries, 5 min delay) |
| Anthropic API fails | Send data-only briefing without AI narrative |
| Email send fails | Mark status "failed", retry task |
| All retries exhausted | Log error, mark status "failed", do not send partial |
| Duplicate briefing attempt | Unique constraint prevents insert, task exits cleanly |

## Cost Estimate

At scale of 100 LOs:
- Haiku API: ~$0.20/day ($6/month)
- Email (SendGrid): ~100 emails/day, well within free tier
- Celery worker: already running for existing tasks
- DB: 6 queries × 100 LOs = 600 queries per morning (~2 seconds total)

## Success Metrics

- **Delivery rate:** % of enabled LOs who receive briefing by their configured hour
- **Open rate:** % of emails opened (via SendGrid tracking)
- **In-app engagement:** % of briefings viewed in-app (`viewed_in_app_at` not null)
- **Target:** 95% delivery rate, 60%+ open rate within first month
