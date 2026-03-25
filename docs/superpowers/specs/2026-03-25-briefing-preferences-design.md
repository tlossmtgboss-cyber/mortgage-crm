# Morning Briefing Preferences Customization — Design Spec

## Goal

Let users control what appears in their morning briefing: toggle sections on/off, adjust thresholds for at-risk and stale lead detection, and choose an AI narrative tone (concise / balanced / detailed). Per-user only, no org-level defaults.

## Decision Log

- **Storage**: JSONB column on User (`briefing_preferences`) — no new tables
- **`briefing_enabled` / `briefing_hour`**: Stay as dedicated columns (used by Celery dispatch for fast SQL filtering)
- **Team/org sections**: Not toggleable — they're level-gated (manager/leadership only), always shown when applicable
- **AI tone**: Three options (concise, balanced, detailed) — not freeform
- **NULL preferences**: Service uses all defaults — zero migration pressure on existing users
- **PUT semantics**: Full-object replacement (not partial merge). Frontend always sends the complete preferences object. A partial payload will have missing fields filled with Pydantic defaults.
- **Extra fields**: Pydantic silently ignores unknown keys (default behavior). No `extra = "forbid"`.
- **`timezone`**: Read-only in this endpoint (managed on User model elsewhere). GET returns it; PUT does not accept it.

## Data Model

### New column on User model (`backend/database/models/core.py`)

```python
from sqlalchemy.dialects.postgresql import JSONB

briefing_preferences = Column(JSONB, nullable=True)  # NULL = all defaults
```

### Default structure (applied in code when NULL or keys missing)

```json
{
  "sections": {
    "pipeline": true,
    "at_risk": true,
    "stale_leads": true,
    "appointments": true,
    "conditions": true,
    "yesterday": true
  },
  "thresholds": {
    "at_risk_days": 10,
    "stale_lead_days": 7,
    "stale_lead_high_score_days": 3,
    "lock_expiring_days": 3,
    "max_at_risk_items": 10,
    "max_stale_lead_items": 10
  },
  "ai_tone": "balanced"
}
```

### Validation constraints

| Field | Type | Min | Max | Default |
|-------|------|-----|-----|---------|
| sections.* | bool | — | — | true |
| thresholds.at_risk_days | int | 1 | 30 | 10 |
| thresholds.stale_lead_days | int | 1 | 30 | 7 |
| thresholds.stale_lead_high_score_days | int | 1 | 14 | 3 |
| thresholds.lock_expiring_days | int | 1 | 14 | 3 |
| thresholds.max_at_risk_items | int | 1 | 20 | 10 |
| thresholds.max_stale_lead_items | int | 1 | 20 | 10 |
| ai_tone | str | — | — | "balanced" (enum: concise, balanced, detailed) |

### Migration

```sql
ALTER TABLE users ADD COLUMN IF NOT EXISTS briefing_preferences JSONB;
```

Single column addition, no data migration needed (NULL = defaults).

## Backend Changes

### Service (`backend/services/morning_briefing_service.py`)

**New: `BriefingPreferences` dataclass**

```python
@dataclass
class BriefingPreferences:
    sections: Dict[str, bool]
    thresholds: Dict[str, int]
    ai_tone: str  # "concise", "balanced", "detailed"
```

**New: `load_preferences(user)` classmethod on `MorningBriefingService`**

Reads `user.briefing_preferences` (JSONB), deep-merges with defaults for any missing keys, returns `BriefingPreferences`. If NULL, returns all defaults.

**Modified: `build_context(db, user, briefing_date, prefs=None)`**

`prefs` parameter is optional — if `None`, `build_context` calls `load_preferences(user)` internally. This preserves backward compatibility for existing callers and tests.

The section-toggle logic lives inside `gather_individual_data()`: pass `prefs` through and check each section flag before its query call. This keeps the existing method structure intact.

- Checks `prefs.sections["pipeline"]` before calling `_query_pipeline_snapshot()`
- Checks `prefs.sections["at_risk"]` before calling `_query_at_risk_loans()`
- Checks `prefs.sections["stale_leads"]` before calling `_query_stale_leads()`
- Checks `prefs.sections["appointments"]` before calling `_query_todays_appointments()`
- Checks `prefs.sections["conditions"]` before calling `_query_conditions()`
- Checks `prefs.sections["yesterday"]` before calling `_query_yesterday_activity()`
- Disabled sections get empty defaults (empty list or empty dict) AND are omitted from the AI prompt in `_format_context_for_ai` (check `prefs.sections` before adding each block)

**Modified: query methods accept threshold params**

Replace hardcoded values with parameters sourced from `prefs.thresholds`:

- `_query_at_risk_loans(db, user_id, org_id, lock_days, stage_days, limit)` — uses `lock_expiring_days`, `at_risk_days`, `max_at_risk_items`
- `_query_stale_leads(db, user_id, org_id, today, lead_days, high_score_days, limit)` — uses `stale_lead_days`, `stale_lead_high_score_days`, `max_stale_lead_items`
- `gather_manager_data` and `gather_leadership_data` also accept `prefs.thresholds` and parameterize their at-risk/lock-expiring queries (lines ~358-376, ~519-539 in current service). When a manager's own preferences set `lock_expiring_days=7`, their team rollup uses that same threshold.

**Modified: `generate_narrative(ctx, ai_tone)`**

Three system prompt variants:

- **Concise**: "You are a mortgage pipeline assistant. Respond in exactly 3 bullet points. Lead with numbers. No filler, no encouragement."
- **Balanced**: Current prompt (unchanged from existing implementation)
- **Detailed**: "You are a mortgage pipeline assistant. Write 2-3 short paragraphs covering priorities, risks, and suggested next actions. Be specific with names and numbers."

### Routes (`backend/routes/briefing_routes.py`)

**New Pydantic schema:**

```python
class BriefingSections(BaseModel):
    pipeline: bool = True
    at_risk: bool = True
    stale_leads: bool = True
    appointments: bool = True
    conditions: bool = True
    yesterday: bool = True

class BriefingThresholds(BaseModel):
    at_risk_days: int = Field(default=10, ge=1, le=30)
    stale_lead_days: int = Field(default=7, ge=1, le=30)
    stale_lead_high_score_days: int = Field(default=3, ge=1, le=14)
    lock_expiring_days: int = Field(default=3, ge=1, le=14)
    max_at_risk_items: int = Field(default=10, ge=1, le=20)
    max_stale_lead_items: int = Field(default=10, ge=1, le=20)

class BriefingPreferencesSchema(BaseModel):
    briefing_enabled: bool = True
    briefing_hour: int = Field(ge=0, le=23, default=7)
    sections: BriefingSections = BriefingSections()
    thresholds: BriefingThresholds = BriefingThresholds()
    ai_tone: Literal["concise", "balanced", "detailed"] = "balanced"
```

**Modified: `GET /preferences`**

Returns flat `briefing_enabled`, `briefing_hour`, `timezone` plus `sections`, `thresholds`, `ai_tone` from `user.briefing_preferences` (merged with defaults).

**Modified: `PUT /preferences`**

Accepts `BriefingPreferencesSchema`. Split-write: `briefing_enabled` and `briefing_hour` go to their dedicated User columns (used by Celery dispatch). `sections`, `thresholds`, `ai_tone` go to `user.briefing_preferences` JSONB. Add an inline comment in the route handler documenting this split.

### Celery task (`backend/tasks/morning_briefing_tasks.py`)

**Modified: `generate_user_briefing`**

After loading user, before calling `build_context`:

```python
prefs = MorningBriefingService.load_preferences(user)
ctx = service.build_context(db, user, briefing_date, prefs)
narrative = service.generate_narrative(ctx, prefs.ai_tone)
```

One import addition, two lines changed.

## Frontend Changes

### Settings.js — Expand existing `MorningBriefingSettings` component

No new files. Extend the component that already exists inside `frontend/src/pages/Settings.js`.

**Preferences state expands:**

```javascript
const [prefs, setPrefs] = useState({
  briefing_enabled: true,
  briefing_hour: 7,
  timezone: '',
  sections: {
    pipeline: true, at_risk: true, stale_leads: true,
    appointments: true, conditions: true, yesterday: true,
  },
  thresholds: {
    at_risk_days: 10, stale_lead_days: 7, stale_lead_high_score_days: 3,
    lock_expiring_days: 3, max_at_risk_items: 10, max_stale_lead_items: 10,
  },
  ai_tone: 'balanced',
});
```

**Three new sub-sections below existing enable/hour controls:**

1. **Sections** — Labeled checkboxes:
   - "Pipeline snapshot" → `sections.pipeline`
   - "At-risk loans" → `sections.at_risk`
   - "Leads going cold" → `sections.stale_leads`
   - "Today's appointments" → `sections.appointments`
   - "Outstanding conditions" → `sections.conditions`
   - "Yesterday's activity" → `sections.yesterday`

2. **Thresholds** — Number inputs with `min`/`max` constraints:
   - "Flag loans stuck longer than ___ days" → `thresholds.at_risk_days` (min=1, max=30)
   - "Flag leads with no contact for ___ days" → `thresholds.stale_lead_days` (min=1, max=30)
   - "Flag high-score leads after ___ days" → `thresholds.stale_lead_high_score_days` (min=1, max=14)
   - "Lock expiration warning ___ days out" → `thresholds.lock_expiring_days` (min=1, max=14)
   - "Max at-risk items shown" → `thresholds.max_at_risk_items` (min=1, max=20)
   - "Max stale lead items shown" → `thresholds.max_stale_lead_items` (min=1, max=20)
   - Threshold inputs disabled when parent section toggled off (at_risk thresholds disabled when `sections.at_risk` is false, etc.)

3. **AI Tone** — Three radio buttons with descriptions:
   - Concise: "Bullet points, numbers only"
   - Balanced: "Short narrative with key highlights" (default)
   - Detailed: "Full paragraphs with suggested actions"

**Behavior:**
- Single "Save Preferences" button saves all fields in one PUT call
- "Generate Now" button stays — lets users preview changes immediately. It reads persisted preferences from the DB, so the user must save before generating. The "Generate Now" button should be disabled when there are unsaved changes (track dirty state).
- All sub-sections disabled when `briefing_enabled` is false

### MorningBriefingCard.js — No changes

The Dashboard card already renders whatever sections the API returns. If a section is disabled, the service returns empty data for it, and the card's conditional rendering (`at_risk && at_risk.length > 0`) already hides empty sections. No frontend card changes needed.

## Files Changed

| File | Change |
|------|--------|
| `backend/database/models/core.py` | Add `briefing_preferences` JSONB column |
| `backend/migrations/add_briefing_preferences.py` | ALTER TABLE migration |
| `backend/services/morning_briefing_service.py` | BriefingPreferences dataclass, load_preferences(), parameterized queries, tone variants |
| `backend/routes/briefing_routes.py` | Expanded Pydantic schemas, updated GET/PUT preferences |
| `backend/tasks/morning_briefing_tasks.py` | Pass preferences to service (2 lines) |
| `frontend/src/pages/Settings.js` | Expand MorningBriefingSettings with sections/thresholds/tone |

## Testing

- Unit tests for `load_preferences()` — NULL input, partial input, full input, invalid keys ignored
- Unit tests for `BriefingPreferences` defaults merging
- Existing 9 tests continue passing (backward compatible — NULL preferences = current behavior)
- Manual: toggle sections off → verify briefing omits them. Change tone → verify narrative style changes.
