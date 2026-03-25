# Morning Briefing Preferences Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users customize their morning briefing — toggle sections on/off, adjust detection thresholds, and choose an AI narrative tone.

**Architecture:** JSONB column `briefing_preferences` on the existing User model stores sections/thresholds/ai_tone. NULL = all defaults. The service deep-merges stored prefs with defaults, then uses them to gate queries and parameterize thresholds. Frontend expands the existing MorningBriefingSettings component in Settings.js.

**Tech Stack:** FastAPI, SQLAlchemy (PostgreSQL JSONB), Pydantic v2, React (functional components), Celery

**Spec:** `docs/superpowers/specs/2026-03-25-briefing-preferences-design.md`

---

## File Structure

| File | Responsibility |
|------|---------------|
| `backend/database/models/core.py` | Add `briefing_preferences` JSONB column to User |
| `backend/migrations/add_briefing_preferences.py` | ALTER TABLE migration |
| `backend/services/morning_briefing_service.py` | BriefingPreferences dataclass, `load_preferences()`, parameterized queries, section gating, tone-based prompts |
| `backend/routes/briefing_routes.py` | Expanded Pydantic schemas, updated GET/PUT preferences endpoints |
| `backend/tasks/morning_briefing_tasks.py` | Pass loaded preferences through to service |
| `frontend/src/pages/Settings.js` | Expand MorningBriefingSettings with sections, thresholds, tone UI |
| `backend/tests/test_briefing_preferences.py` | Unit tests for preferences loading, merging, validation |

---

### Task 1: Database — Add `briefing_preferences` JSONB column

**Files:**
- Modify: `backend/database/models/core.py:122-127`
- Create: `backend/migrations/add_briefing_preferences.py`

- [ ] **Step 1: Add JSONB column to User model**

In `backend/database/models/core.py`, add the import and column. The column goes after `briefing_hour` (line 124):

```python
# At top of file, add to imports:
from sqlalchemy.dialects.postgresql import JSONB

# After line 124 (briefing_hour), add:
    briefing_preferences = Column(JSONB, nullable=True)  # NULL = all defaults
```

The existing import line (line 15-18) has:
```python
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Date,
    Text, ForeignKey, JSON, UniqueConstraint, Index
)
```
Add a new import line below it:
```python
from sqlalchemy.dialects.postgresql import JSONB
```

- [ ] **Step 2: Create migration script**

Create `backend/migrations/add_briefing_preferences.py`:

```python
"""
Migration: Add briefing_preferences JSONB column to users table.

Stores user customization for morning briefings: section toggles,
detection thresholds, and AI narrative tone. NULL = all defaults.
"""

import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)


def run_migration(engine):
    """Add briefing_preferences column to users if it doesn't exist."""
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'users'
              AND column_name = 'briefing_preferences'
        """))
        if result.fetchone():
            logger.info("Column briefing_preferences already exists on users, skipping")
            return

        conn.execute(text("""
            ALTER TABLE users ADD COLUMN briefing_preferences JSONB;
        """))
        conn.commit()
        logger.info("Added briefing_preferences JSONB column to users table")
```

- [ ] **Step 3: Wire migration into startup**

In `backend/database/init_db.py`, add near the end of the migration section (after the last `try/except` migration block, around line ~1715):

```python
        # Add briefing_preferences JSONB column to users
        try:
            from migrations.add_briefing_preferences import run_migration as run_briefing_prefs
            run_briefing_prefs(_engine)
            logger.info("✅ briefing_preferences column ready")
        except Exception as e:
            logger.warning(f"⚠️ briefing_preferences migration note: {e}")
```

- [ ] **Step 4: Verify model loads without errors**

Run: `.venv/bin/python3 -c "from database.models.core import User; print('briefing_preferences' in [c.name for c in User.__table__.columns])"`
(Run from `backend/` directory)
Expected: `True`

- [ ] **Step 5: Commit**

```bash
git add backend/database/models/core.py backend/migrations/add_briefing_preferences.py backend/database/init_db.py
git commit -m "feat: add briefing_preferences JSONB column to User model"
```

---

### Task 2: Service — BriefingPreferences dataclass and `load_preferences()`

**Files:**
- Modify: `backend/services/morning_briefing_service.py:1-17` (imports/top), add new code after line 38
- Test: `backend/tests/test_briefing_preferences.py`

- [ ] **Step 1: Write failing tests for load_preferences**

Create `backend/tests/test_briefing_preferences.py`:

```python
"""Tests for BriefingPreferences loading and merging."""
import pytest


class MockUser:
    """Minimal mock for User model."""
    def __init__(self, briefing_preferences=None):
        self.briefing_preferences = briefing_preferences


class TestLoadPreferences:
    """Test MorningBriefingService.load_preferences()."""

    def _load(self, raw_prefs=None):
        from services.morning_briefing_service import MorningBriefingService
        user = MockUser(briefing_preferences=raw_prefs)
        return MorningBriefingService.load_preferences(user)

    def test_null_returns_all_defaults(self):
        prefs = self._load(None)
        assert prefs.ai_tone == "balanced"
        assert prefs.sections["pipeline"] is True
        assert prefs.sections["at_risk"] is True
        assert prefs.sections["stale_leads"] is True
        assert prefs.sections["appointments"] is True
        assert prefs.sections["conditions"] is True
        assert prefs.sections["yesterday"] is True
        assert prefs.thresholds["at_risk_days"] == 10
        assert prefs.thresholds["stale_lead_days"] == 7
        assert prefs.thresholds["stale_lead_high_score_days"] == 3
        assert prefs.thresholds["lock_expiring_days"] == 3
        assert prefs.thresholds["max_at_risk_items"] == 10
        assert prefs.thresholds["max_stale_lead_items"] == 10

    def test_partial_sections_fills_defaults(self):
        prefs = self._load({"sections": {"pipeline": False}})
        assert prefs.sections["pipeline"] is False
        assert prefs.sections["at_risk"] is True  # default
        assert prefs.thresholds["at_risk_days"] == 10  # default

    def test_partial_thresholds_fills_defaults(self):
        prefs = self._load({"thresholds": {"at_risk_days": 20}})
        assert prefs.thresholds["at_risk_days"] == 20
        assert prefs.thresholds["stale_lead_days"] == 7  # default

    def test_ai_tone_preserved(self):
        prefs = self._load({"ai_tone": "concise"})
        assert prefs.ai_tone == "concise"

    def test_ai_tone_invalid_falls_back(self):
        prefs = self._load({"ai_tone": "verbose"})
        assert prefs.ai_tone == "balanced"

    def test_full_override(self):
        full = {
            "sections": {
                "pipeline": False, "at_risk": False, "stale_leads": False,
                "appointments": True, "conditions": True, "yesterday": False,
            },
            "thresholds": {
                "at_risk_days": 5, "stale_lead_days": 14,
                "stale_lead_high_score_days": 7, "lock_expiring_days": 7,
                "max_at_risk_items": 5, "max_stale_lead_items": 5,
            },
            "ai_tone": "detailed",
        }
        prefs = self._load(full)
        assert prefs.sections["pipeline"] is False
        assert prefs.thresholds["at_risk_days"] == 5
        assert prefs.ai_tone == "detailed"

    def test_unknown_keys_ignored(self):
        prefs = self._load({"unknown_key": "whatever", "sections": {"fake": True}})
        assert prefs.ai_tone == "balanced"
        assert "fake" not in prefs.sections
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ../.venv/bin/python3 -m pytest tests/test_briefing_preferences.py -v`
Expected: FAIL — `load_preferences` doesn't exist yet

- [ ] **Step 3: Implement BriefingPreferences and load_preferences**

In `backend/services/morning_briefing_service.py`, add after the existing imports (line 12):

```python
from copy import deepcopy
```

Then add after the `MANAGER_ROLES` tuple (after line 38), before the `BriefingContext` dataclass:

```python
# ------------------------------------------------------------------
# Briefing preferences (user-customizable)
# ------------------------------------------------------------------

VALID_AI_TONES = ("concise", "balanced", "detailed")

DEFAULT_BRIEFING_PREFERENCES = {
    "sections": {
        "pipeline": True,
        "at_risk": True,
        "stale_leads": True,
        "appointments": True,
        "conditions": True,
        "yesterday": True,
    },
    "thresholds": {
        "at_risk_days": 10,
        "stale_lead_days": 7,
        "stale_lead_high_score_days": 3,
        "lock_expiring_days": 3,
        "max_at_risk_items": 10,
        "max_stale_lead_items": 10,
    },
    "ai_tone": "balanced",
}


@dataclass
class BriefingPreferences:
    """User-customizable briefing settings."""
    sections: Dict[str, bool] = field(default_factory=lambda: deepcopy(DEFAULT_BRIEFING_PREFERENCES["sections"]))
    thresholds: Dict[str, int] = field(default_factory=lambda: deepcopy(DEFAULT_BRIEFING_PREFERENCES["thresholds"]))
    ai_tone: str = "balanced"
```

Then add `load_preferences` as a staticmethod on `MorningBriefingService` (after `compute_health`, before `gather_individual_data`):

```python
    @staticmethod
    def load_preferences(user: Any) -> BriefingPreferences:
        """Load and merge user briefing preferences with defaults.

        Reads user.briefing_preferences (JSONB). Deep-merges with defaults
        for any missing keys. Returns BriefingPreferences with all fields
        populated. If NULL, returns all defaults.
        """
        raw = getattr(user, "briefing_preferences", None)
        if not raw or not isinstance(raw, dict):
            return BriefingPreferences()

        defaults = deepcopy(DEFAULT_BRIEFING_PREFERENCES)

        # Merge sections — only keep known keys
        merged_sections = dict(defaults["sections"])
        raw_sections = raw.get("sections")
        if isinstance(raw_sections, dict):
            for key in merged_sections:
                if key in raw_sections and isinstance(raw_sections[key], bool):
                    merged_sections[key] = raw_sections[key]

        # Merge thresholds — only keep known keys
        merged_thresholds = dict(defaults["thresholds"])
        raw_thresholds = raw.get("thresholds")
        if isinstance(raw_thresholds, dict):
            for key in merged_thresholds:
                if key in raw_thresholds and isinstance(raw_thresholds[key], int):
                    merged_thresholds[key] = raw_thresholds[key]

        # AI tone — validate against allowed values
        ai_tone = raw.get("ai_tone", "balanced")
        if ai_tone not in VALID_AI_TONES:
            ai_tone = "balanced"

        return BriefingPreferences(
            sections=merged_sections,
            thresholds=merged_thresholds,
            ai_tone=ai_tone,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && ../.venv/bin/python3 -m pytest tests/test_briefing_preferences.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/morning_briefing_service.py backend/tests/test_briefing_preferences.py
git commit -m "feat: add BriefingPreferences dataclass and load_preferences()"
```

---

### Task 3: Service — Parameterize queries and add section gating

**Files:**
- Modify: `backend/services/morning_briefing_service.py:96-119` (gather_individual_data), `:154-174` (_query_at_risk_loans), `:202-218` (_query_stale_leads), `:321-376` (gather_manager_data at-risk query), `:458-539` (gather_leadership_data at-risk queries), `:581-616` (build_context)

This task has no new tests — it refactors internal query methods to accept parameters. Existing behavior is preserved when defaults are used (backward-compatible).

- [ ] **Step 1: Modify `gather_individual_data` to accept and use `prefs`**

Change the signature and body of `gather_individual_data` (currently lines 96-119):

```python
    def gather_individual_data(
        self, db: Session, user_id: int, org_id: int, briefing_date: date, user_tz: str,
        prefs: Optional['BriefingPreferences'] = None,
    ) -> Dict[str, Any]:
        """Run queries for individual-level briefing data. Skips disabled sections."""
        if prefs is None:
            prefs = BriefingPreferences()

        today = briefing_date
        yesterday = today - timedelta(days=1)
        week_ahead = today + timedelta(days=7)
        lock_cutoff = today + timedelta(days=prefs.thresholds["lock_expiring_days"])

        pipeline = self._query_pipeline_snapshot(db, user_id, org_id, week_ahead) if prefs.sections["pipeline"] else {"active_count": 0, "total_volume": 0, "closing_soon": 0, "by_stage": {}}
        at_risk = self._query_at_risk_loans(db, user_id, org_id, lock_cutoff, prefs.thresholds["at_risk_days"], prefs.thresholds["max_at_risk_items"]) if prefs.sections["at_risk"] else []
        stale_leads = self._query_stale_leads(db, user_id, org_id, today, prefs.thresholds["stale_lead_days"], prefs.thresholds["stale_lead_high_score_days"], prefs.thresholds["max_stale_lead_items"]) if prefs.sections["stale_leads"] else []
        appointments = self._query_todays_appointments(db, user_id, org_id, today, user_tz) if prefs.sections["appointments"] else []
        conditions = self._query_pending_conditions(db, user_id, org_id, today) if prefs.sections["conditions"] else []
        yesterday_activity = self._query_yesterday_activity(db, user_id, org_id, yesterday) if prefs.sections["yesterday"] else {"funded": 0, "new_loans": 0, "conversions": 0}

        return {
            "pipeline": pipeline,
            "at_risk": at_risk,
            "stale_leads": stale_leads,
            "appointments": appointments,
            "conditions": conditions,
            "yesterday": yesterday_activity,
        }
```

- [ ] **Step 2: Parameterize `_query_at_risk_loans`**

Change signature from:
```python
def _query_at_risk_loans(self, db: Session, user_id: int, org_id: int, three_days: date) -> List[Dict]:
```
To:
```python
def _query_at_risk_loans(self, db: Session, user_id: int, org_id: int, lock_cutoff: date, at_risk_days: int = 10, max_items: int = 10) -> List[Dict]:
```

In the SQL query body, replace the hardcoded values:
- Replace `> 10` with `:at_risk_days` (the `days_in_stage` threshold on line 168)
- Replace `LIMIT 10` with `LIMIT :max_items` (line 173)
- Replace the `three_days` variable name with `lock_cutoff` throughout
- Add `at_risk_days` and `max_items` to the query params dict

The SQL becomes (line 158-174):
```python
            rows = db.execute(sa_text(f"""
                SELECT
                    id, loan_number, borrower_name, UPPER(stage) as stage,
                    stage_changed_at, lock_expiration_date,
                    EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - stage_changed_at)) / 86400 as days_in_stage
                FROM loans
                WHERE loan_officer_id = :uid AND organization_id = :oid
                  AND (stage IS NULL OR UPPER(stage) NOT IN ({terminal}))
                  AND (
                    lock_expiration_date <= :lock_cutoff
                    OR EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - stage_changed_at)) / 86400 > :at_risk_days
                  )
                ORDER BY
                    CASE WHEN lock_expiration_date <= :lock_cutoff THEN 0 ELSE 1 END,
                    days_in_stage DESC
                LIMIT :max_items
            """), {"uid": user_id, "oid": org_id, "lock_cutoff": lock_cutoff, "at_risk_days": at_risk_days, "max_items": max_items}).fetchall()
```

Also update the reason-building logic (line 186): change `if days > 10 and not reason:` to `if days > at_risk_days and not reason:` (preserve the `and not reason:` guard).

- [ ] **Step 3: Parameterize `_query_stale_leads`**

Change signature from:
```python
def _query_stale_leads(self, db: Session, user_id: int, org_id: int, today: date) -> List[Dict]:
```
To:
```python
def _query_stale_leads(self, db: Session, user_id: int, org_id: int, today: date, lead_days: int = 7, high_score_days: int = 3, max_items: int = 10) -> List[Dict]:
```

Replace the hardcoded SQL intervals (lines 213-214):
```sql
(ai_score >= 70 AND last_contact < CURRENT_DATE - INTERVAL '3 days')
OR last_contact < CURRENT_DATE - INTERVAL '7 days'
```
With parameterized:
```sql
(ai_score >= 70 AND last_contact < CURRENT_DATE - make_interval(days => :high_score_days))
OR last_contact < CURRENT_DATE - make_interval(days => :lead_days)
```

Replace `LIMIT 10` with `LIMIT :max_items`.

Add params: `"lead_days": lead_days, "high_score_days": high_score_days, "max_items": max_items` to the execute call.

- [ ] **Step 4: Parameterize manager at-risk queries**

In `gather_manager_data` (line 321), change the signature to accept thresholds:
```python
def gather_manager_data(self, db: Session, user_id: int, org_id: int, briefing_date: date, prefs: Optional['BriefingPreferences'] = None) -> Dict:
```

Replace `three_days = today + timedelta(days=3)` with:
```python
if prefs is None:
    prefs = BriefingPreferences()
lock_cutoff = today + timedelta(days=prefs.thresholds["lock_expiring_days"])
at_risk_days = prefs.thresholds["at_risk_days"]
```

There are THREE SQL queries in this method that need parameterization:

**Query 1 — at_risk_counts (lines 358-376):**
- Replace `:three_days` → `:lock_cutoff`, `> 10` → `:at_risk_days`
- Add `"lock_cutoff": lock_cutoff, "at_risk_days": at_risk_days` to params

**Query 2 — stale_counts (lines 381-388):**
- Replace `INTERVAL '7 days'` → `make_interval(days => :lead_days)`
- Add `"lead_days": prefs.thresholds["stale_lead_days"]` to params

**Query 3 — attention items (lines 414-430):**
- Replace `:three_days` → `:lock_cutoff`, `> 10` → `:at_risk_days`
- Add `"lock_cutoff": lock_cutoff, "at_risk_days": at_risk_days` to params

Also update the Python logic at line 438: change `float(r[5] or 0) > 10` to `float(r[5] or 0) > at_risk_days`

- [ ] **Step 5: Parameterize leadership at-risk queries**

In `gather_leadership_data` (line 458), change the signature:
```python
def gather_leadership_data(self, db: Session, org_id: int, briefing_date: date, prefs: Optional['BriefingPreferences'] = None) -> Dict:
```

Replace `three_days = today + timedelta(days=3)` with:
```python
if prefs is None:
    prefs = BriefingPreferences()
lock_cutoff = today + timedelta(days=prefs.thresholds["lock_expiring_days"])
at_risk_days = prefs.thresholds["at_risk_days"]
```

There are THREE SQL queries plus one Python line that need parameterization:

**Query 1 — branch comparison (lines 487-503):**
- Replace `:three_days` → `:lock_cutoff`, `> 10` → `:at_risk_days`

**Query 2 — top_risks (lines 519-539):**
- Replace `:three_days` → `:lock_cutoff`, `> 10` → `:at_risk_days`

**Query 3 — org_snap (lines 468-475):** No changes needed (no threshold refs).

**Python logic — branch health computation (line 515):**
- Change `sla_breach=avg_days > 10` to `sla_breach=avg_days > at_risk_days`

Add `"lock_cutoff": lock_cutoff, "at_risk_days": at_risk_days` to params for queries 1 and 2.

- [ ] **Step 6: Update `build_context` to accept and pass `prefs`**

Change signature (line 581-582):
```python
    def build_context(
        self, db: Session, user: Any, briefing_date: date, prefs: Optional[BriefingPreferences] = None,
    ) -> BriefingContext:
```

Add at the start of the method body (after line 588):
```python
        if prefs is None:
            prefs = self.load_preferences(user)
```

Pass `prefs` to `gather_individual_data` (line 600):
```python
        individual = self.gather_individual_data(db, user_id, org_id, briefing_date, user_tz, prefs)
```

Pass `prefs` to `gather_manager_data` (line 610):
```python
            ctx.team = self.gather_manager_data(db, user_id, org_id, briefing_date, prefs)
```

Pass `prefs` to `gather_leadership_data` (line 614):
```python
            ctx.team = self.gather_leadership_data(db, org_id, briefing_date, prefs)
```

- [ ] **Step 7: Verify no syntax errors**

Run: `cd backend && ../.venv/bin/python3 -c "from services.morning_briefing_service import MorningBriefingService; print('OK')"`
Expected: `OK`

- [ ] **Step 8: Commit**

```bash
git add backend/services/morning_briefing_service.py
git commit -m "feat: parameterize briefing queries with user preferences"
```

---

### Task 4: Service — AI tone variants and section-aware prompt formatting

**Files:**
- Modify: `backend/services/morning_briefing_service.py:622-660` (prompts and generate_narrative), `:684-767` (_format_context_for_ai)
- Modify: `backend/tests/test_briefing_preferences.py` (add tone tests)

- [ ] **Step 1: Write failing tests for tone selection**

Add to `backend/tests/test_briefing_preferences.py`:

```python
class TestTonePrompts:
    """Test that AI tone selection produces different system prompts."""

    def _get_prompts(self):
        from services.morning_briefing_service import MorningBriefingService
        return {
            "concise": MorningBriefingService.TONE_PROMPTS["concise"],
            "balanced": MorningBriefingService.INDIVIDUAL_SYSTEM_PROMPT,
            "detailed": MorningBriefingService.TONE_PROMPTS["detailed"],
        }

    def test_concise_prompt_exists(self):
        prompts = self._get_prompts()
        assert "bullet" in prompts["concise"].lower()

    def test_detailed_prompt_exists(self):
        prompts = self._get_prompts()
        assert "paragraph" in prompts["detailed"].lower()

    def test_balanced_is_default_individual(self):
        prompts = self._get_prompts()
        assert "3 prioritized actions" in prompts["balanced"]

    def test_tone_prompts_are_modifiers(self):
        """Tone prompts should be appended to level prompts, not replace them."""
        prompts = self._get_prompts()
        # They should NOT start with "You are" — they're format overrides
        assert not prompts["concise"].startswith("You are")
        assert not prompts["detailed"].startswith("You are")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ../.venv/bin/python3 -m pytest tests/test_briefing_preferences.py::TestTonePrompts -v`
Expected: FAIL — `TONE_PROMPTS` doesn't exist

- [ ] **Step 3: Add tone prompt variants**

In `backend/services/morning_briefing_service.py`, after the existing `LEADERSHIP_SYSTEM_PROMPT` (after line 646), add:

```python
    TONE_PROMPTS = {
        "concise": (
            "FORMAT OVERRIDE: Respond in exactly 3 bullet points. "
            "Lead with numbers. No filler, no encouragement."
        ),
        "detailed": (
            "FORMAT OVERRIDE: Write 2-3 short paragraphs covering "
            "priorities, risks, and suggested next actions. Be specific with names and numbers."
        ),
    }
```

- [ ] **Step 4: Modify `generate_narrative` to accept `ai_tone`**

Change the signature (line 648):
```python
    def generate_narrative(self, ctx: BriefingContext, ai_tone: str = "balanced") -> Optional[str]:
```

Change the system prompt selection (lines 656-660):
```python
        # Select base prompt by level
        system_prompt = {
            "individual": self.INDIVIDUAL_SYSTEM_PROMPT,
            "manager": self.MANAGER_SYSTEM_PROMPT,
            "leadership": self.LEADERSHIP_SYSTEM_PROMPT,
        }.get(ctx.level, self.INDIVIDUAL_SYSTEM_PROMPT)

        # Append tone modifier (preserves level-specific context guidance)
        if ai_tone in self.TONE_PROMPTS:
            system_prompt = system_prompt + "\n\n" + self.TONE_PROMPTS[ai_tone]
```

This appends the tone instruction to the level-specific prompt rather than replacing it, so a leadership user selecting "concise" still gets guidance about org-level analysis.

- [ ] **Step 5: Make `_format_context_for_ai` section-aware**

Change signature (line 684):
```python
    def _format_context_for_ai(self, ctx: BriefingContext, prefs: Optional[BriefingPreferences] = None) -> str:
```

Add at top of method:
```python
        if prefs is None:
            prefs = BriefingPreferences()
```

Wrap each section with a preference check:

For Pipeline (line 690): wrap with `if prefs.sections.get("pipeline", True):`
For At-risk (line 699): wrap with `if prefs.sections.get("at_risk", True) and ctx.at_risk:`
For Stale leads (line 706): wrap with `if prefs.sections.get("stale_leads", True) and ctx.stale_leads:`
For Appointments (line 713): wrap with `if prefs.sections.get("appointments", True) and ctx.appointments:`
For Conditions (line 720): wrap with `if prefs.sections.get("conditions", True) and ctx.conditions:`
For Yesterday (line 728): wrap with `if prefs.sections.get("yesterday", True):`

Update `generate_narrative` signature to also accept `prefs`:

```python
    def generate_narrative(self, ctx: BriefingContext, ai_tone: str = "balanced", prefs: Optional[BriefingPreferences] = None) -> Optional[str]:
```

And update the call to `_format_context_for_ai`:
```python
        user_prompt = self._format_context_for_ai(ctx, prefs)
```

- [ ] **Step 6: Run all tests**

Run: `cd backend && ../.venv/bin/python3 -m pytest tests/test_briefing_preferences.py -v`
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add backend/services/morning_briefing_service.py backend/tests/test_briefing_preferences.py
git commit -m "feat: add AI tone variants and section-aware prompt formatting"
```

---

### Task 5: Routes — Expanded Pydantic schemas and updated GET/PUT preferences

**Files:**
- Modify: `backend/routes/briefing_routes.py:1-39` (imports, schemas), `:214-242` (GET/PUT preferences)

- [ ] **Step 1: Expand Pydantic schemas**

In `backend/routes/briefing_routes.py`, replace the existing `BriefingPreferences` schema (lines 36-38) with the expanded schemas. Add `Literal` to the imports:

Replace line 19:
```python
from pydantic import BaseModel, Field
```
With:
```python
from typing import Literal
from pydantic import BaseModel, Field
```

Replace lines 36-38 (this removes the old `BriefingPreferences` Pydantic model — note: the service file has a *different* `BriefingPreferences` which is a dataclass, not a Pydantic model):
```python
class BriefingPreferences(BaseModel):
    briefing_enabled: bool = True
    briefing_hour: int = Field(ge=0, le=23, default=7)
```
With:
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

- [ ] **Step 2: Update GET /preferences to return full preferences**

Replace the `get_preferences` route (lines 214-224):

```python
@router.get("/preferences")
async def get_preferences(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get briefing preferences (merged with defaults)."""
    from services.morning_briefing_service import MorningBriefingService
    prefs = MorningBriefingService.load_preferences(current_user)
    return {
        "briefing_enabled": getattr(current_user, "briefing_enabled", True) if current_user.briefing_enabled is not None else True,
        "briefing_hour": getattr(current_user, "briefing_hour", 7) or 7,
        "timezone": getattr(current_user, "timezone", "America/New_York"),
        "sections": prefs.sections,
        "thresholds": prefs.thresholds,
        "ai_tone": prefs.ai_tone,
    }
```

- [ ] **Step 3: Update PUT /preferences to write JSONB**

Replace the `update_preferences` route (lines 227-242):

```python
@router.put("/preferences")
async def update_preferences(
    prefs: BriefingPreferencesSchema,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Update briefing preferences.

    Split-write: briefing_enabled and briefing_hour go to dedicated User columns
    (used by Celery dispatch for fast SQL filtering). sections, thresholds, and
    ai_tone go to user.briefing_preferences JSONB.
    """
    # Dedicated columns (fast SQL filtering by Celery dispatch)
    current_user.briefing_enabled = prefs.briefing_enabled
    current_user.briefing_hour = prefs.briefing_hour

    # JSONB column (customization preferences)
    current_user.briefing_preferences = {
        "sections": prefs.sections.model_dump(),
        "thresholds": prefs.thresholds.model_dump(),
        "ai_tone": prefs.ai_tone,
    }
    db.commit()

    from services.morning_briefing_service import MorningBriefingService
    loaded = MorningBriefingService.load_preferences(current_user)
    return {
        "briefing_enabled": current_user.briefing_enabled,
        "briefing_hour": current_user.briefing_hour,
        "timezone": getattr(current_user, "timezone", "America/New_York"),
        "sections": loaded.sections,
        "thresholds": loaded.thresholds,
        "ai_tone": loaded.ai_tone,
    }
```

- [ ] **Step 4: Verify no syntax errors**

Run: `cd backend && ../.venv/bin/python3 -c "from routes.briefing_routes import router; print('OK')"`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add backend/routes/briefing_routes.py
git commit -m "feat: expand briefing preferences API with sections, thresholds, tone"
```

---

### Task 6: Celery task — Pass preferences through to service

**Files:**
- Modify: `backend/tasks/morning_briefing_tasks.py:145-213`

- [ ] **Step 1: Update generate_user_briefing to load and pass preferences**

In `backend/tasks/morning_briefing_tasks.py`, modify the `generate_user_briefing` function.

After the user is loaded (line 160, `user = db.query(User)...`), add:

```python
        # Load user preferences (NULL = all defaults)
        prefs = MorningBriefingService.load_preferences(user)
```

Change line 196 from:
```python
        ctx = service.build_context(db, user, briefing_date)
```
To:
```python
        ctx = service.build_context(db, user, briefing_date, prefs)
```

Change line 211 from:
```python
        narrative = service.generate_narrative(ctx)
```
To:
```python
        narrative = service.generate_narrative(ctx, prefs.ai_tone, prefs)
```

- [ ] **Step 2: Verify no syntax errors**

Run: `cd backend && ../.venv/bin/python3 -c "from tasks.morning_briefing_tasks import generate_user_briefing; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/tasks/morning_briefing_tasks.py
git commit -m "feat: pass user preferences through Celery task to briefing service"
```

---

### Task 7: Frontend — Expand MorningBriefingSettings with sections, thresholds, tone

**Files:**
- Modify: `frontend/src/pages/Settings.js:2648-2764`

- [ ] **Step 1: Expand preferences state**

Replace line 2649:
```javascript
    const [prefs, setPrefs] = useState({ briefing_enabled: true, briefing_hour: 7, timezone: '' });
```
With:
```javascript
    const [prefs, setPrefs] = useState({
      briefing_enabled: true, briefing_hour: 7, timezone: '',
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
    const [savedPrefs, setSavedPrefs] = useState(null);
```

- [ ] **Step 2: Track dirty state for Generate Now button**

After the `setSavedPrefs` line, add a computed dirty check:

```javascript
    const isDirty = savedPrefs !== null && JSON.stringify(prefs) !== JSON.stringify(savedPrefs);
```

In the `useEffect` fetchPrefs handler, after `setPrefs(data)` (line 2663), add:
```javascript
            setSavedPrefs(data);
```

In `savePrefs`, after the `if (res.ok)` block (line 2683-2684), add:
```javascript
          setSavedPrefs({ ...prefs });
```

- [ ] **Step 3: Expand the PUT body to send all preferences**

Replace the `savePrefs` body (line 2678-2681):
```javascript
          body: JSON.stringify({
            briefing_enabled: prefs.briefing_enabled,
            briefing_hour: prefs.briefing_hour,
          }),
```
With:
```javascript
          body: JSON.stringify({
            briefing_enabled: prefs.briefing_enabled,
            briefing_hour: prefs.briefing_hour,
            sections: prefs.sections,
            thresholds: prefs.thresholds,
            ai_tone: prefs.ai_tone,
          }),
```

- [ ] **Step 4: Add section toggles, threshold inputs, and tone selector to the JSX**

After the delivery time `settings-row` div (before line 2748, the `settings-actions` div), insert the three new sub-sections:

```jsx
        {prefs.briefing_enabled && (
          <>
            {/* Section Toggles */}
            <div className="settings-row" style={{ flexDirection: 'column', alignItems: 'flex-start', gap: '6px' }}>
              <label style={{ fontWeight: 600, marginBottom: '4px' }}>Briefing Sections</label>
              {[
                { key: 'pipeline', label: 'Pipeline snapshot' },
                { key: 'at_risk', label: 'At-risk loans' },
                { key: 'stale_leads', label: 'Leads going cold' },
                { key: 'appointments', label: "Today's appointments" },
                { key: 'conditions', label: 'Outstanding conditions' },
                { key: 'yesterday', label: "Yesterday's activity" },
              ].map(({ key, label }) => (
                <label key={key} className="settings-toggle" style={{ marginLeft: '8px' }}>
                  <input
                    type="checkbox"
                    checked={prefs.sections?.[key] ?? true}
                    onChange={(e) => setPrefs({ ...prefs, sections: { ...prefs.sections, [key]: e.target.checked } })}
                  />
                  <span>{label}</span>
                </label>
              ))}
            </div>

            {/* Threshold Inputs */}
            <div className="settings-row" style={{ flexDirection: 'column', alignItems: 'flex-start', gap: '8px' }}>
              <label style={{ fontWeight: 600, marginBottom: '4px' }}>Detection Thresholds</label>
              {[
                { key: 'at_risk_days', label: 'Flag loans stuck longer than', suffix: 'days', min: 1, max: 30, section: 'at_risk' },
                { key: 'stale_lead_days', label: 'Flag leads with no contact for', suffix: 'days', min: 1, max: 30, section: 'stale_leads' },
                { key: 'stale_lead_high_score_days', label: 'Flag high-score leads after', suffix: 'days', min: 1, max: 14, section: 'stale_leads' },
                { key: 'lock_expiring_days', label: 'Lock expiration warning', suffix: 'days out', min: 1, max: 14, section: 'at_risk' },
                { key: 'max_at_risk_items', label: 'Max at-risk items shown', suffix: '', min: 1, max: 20, section: 'at_risk' },
                { key: 'max_stale_lead_items', label: 'Max stale lead items shown', suffix: '', min: 1, max: 20, section: 'stale_leads' },
              ].map(({ key, label, suffix, min, max, section }) => (
                <div key={key} style={{ display: 'flex', alignItems: 'center', gap: '8px', marginLeft: '8px', opacity: prefs.sections?.[section] === false ? 0.5 : 1 }}>
                  <span style={{ minWidth: '220px' }}>{label}</span>
                  <input
                    type="number"
                    value={prefs.thresholds?.[key] ?? ''}
                    min={min}
                    max={max}
                    disabled={prefs.sections?.[section] === false}
                    onChange={(e) => {
                      const val = parseInt(e.target.value);
                      if (!isNaN(val) && val >= min && val <= max) {
                        setPrefs({ ...prefs, thresholds: { ...prefs.thresholds, [key]: val } });
                      }
                    }}
                    style={{ width: '60px', padding: '4px 8px' }}
                  />
                  {suffix && <span style={{ color: '#666' }}>{suffix}</span>}
                </div>
              ))}
            </div>

            {/* AI Tone */}
            <div className="settings-row" style={{ flexDirection: 'column', alignItems: 'flex-start', gap: '6px' }}>
              <label style={{ fontWeight: 600, marginBottom: '4px' }}>AI Narrative Tone</label>
              {[
                { value: 'concise', label: 'Concise', desc: 'Bullet points, numbers only' },
                { value: 'balanced', label: 'Balanced', desc: 'Short narrative with key highlights' },
                { value: 'detailed', label: 'Detailed', desc: 'Full paragraphs with suggested actions' },
              ].map(({ value, label, desc }) => (
                <label key={value} style={{ display: 'flex', alignItems: 'center', gap: '8px', marginLeft: '8px', cursor: 'pointer' }}>
                  <input
                    type="radio"
                    name="ai_tone"
                    value={value}
                    checked={prefs.ai_tone === value}
                    onChange={() => setPrefs({ ...prefs, ai_tone: value })}
                  />
                  <span><strong>{label}</strong> — {desc}</span>
                </label>
              ))}
            </div>
          </>
        )}
```

- [ ] **Step 5: Disable Generate Now when dirty**

Update the Generate Now button (line 2752) — change:
```javascript
            <button onClick={generateNow} disabled={generating || !prefs.briefing_enabled} className="btn btn-secondary">
```
To:
```javascript
            <button onClick={generateNow} disabled={generating || !prefs.briefing_enabled || isDirty} className="btn btn-secondary" title={isDirty ? 'Save preferences first' : ''}>
```

- [ ] **Step 6: Verify frontend builds**

Run: `cd frontend && npm run build 2>&1 | tail -5`
Expected: Build succeeds (or at least no syntax errors in Settings.js)

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/Settings.js
git commit -m "feat: expand Morning Briefing settings with section toggles, thresholds, AI tone"
```

---

### Task 8: Final verification — all tests pass, end-to-end check

**Files:**
- Read: all modified files for quick sanity check

- [ ] **Step 1: Run all briefing preference tests**

Run: `cd backend && ../.venv/bin/python3 -m pytest tests/test_briefing_preferences.py -v`
Expected: All tests PASS

- [ ] **Step 2: Verify model import chain**

Run: `cd backend && ../.venv/bin/python3 -c "from database.models.core import User; u = User(); print(type(u.briefing_preferences))"`
Expected: `<class 'NoneType'>` (NULL default)

- [ ] **Step 3: Verify routes import cleanly**

Run: `cd backend && ../.venv/bin/python3 -c "from routes.briefing_routes import router; print(len(router.routes), 'routes')"`
Expected: `6 routes`

- [ ] **Step 4: Verify service loads cleanly with new code**

Run: `cd backend && ../.venv/bin/python3 -c "from services.morning_briefing_service import MorningBriefingService, BriefingPreferences; prefs = BriefingPreferences(); print(prefs.ai_tone, len(prefs.sections), len(prefs.thresholds))"`
Expected: `balanced 6 6`

- [ ] **Step 5: Final commit if any fixups needed**

```bash
git add -A
git commit -m "fix: address any issues found during verification"
```
(Skip if no changes needed)
