# Aria Interactive Briefing System — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the V1 interactive morning briefing system — a 5-step email conversation loop where Aria proposes tasks, the LO replies, Aria confirms, the LO approves, Aria executes, and Aria reports results.

**Architecture:** Three-phase delivery: (1) land 7 audit fixes on the existing morning briefing code, (2) build the interactive briefing system (models → services → Celery tasks → templates → routes), (3) wire feature flags for gradual rollout. All email flows via Microsoft Graph from `aria@perenniaai.com`. Reply parsing uses Claude Haiku with Pydantic structured output. State machine enforces the conversation loop with idempotent transitions.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 (PostgreSQL), Celery + Redis, Microsoft Graph API (app-only tokens), Claude Haiku 4.5 (reply parsing), React 18.

**Spec:** `docs/superpowers/specs/2026-05-07-interactive-morning-briefing-design.md`

---

## File Structure

### New files (backend)

| File | Responsibility |
|------|---------------|
| `backend/database/models/briefing_thread.py` | `BriefingThread`, `BriefingTask`, `BriefingAuditLog` SQLAlchemy models |
| `backend/schemas/briefing_thread.py` | Pydantic schemas: `ParsedReply`, `ItemOverride`, request/response DTOs |
| `backend/services/briefing_thread_service.py` | State machine transitions, thread lifecycle, idempotency guards |
| `backend/services/briefing_reply_parser.py` | Quoted-reply stripping, Claude Haiku call, `ParsedReply` extraction |
| `backend/services/briefing_executor.py` | Pre-flight validation, tool dispatch, risk gating |
| `backend/services/briefing_audit_service.py` | Chained-hash audit log writes, compliance flag checks |
| `backend/services/briefing_email_renderer.py` | Confirmation + results email HTML templates |
| `backend/services/aria_mailbox_service.py` | Graph app-only token management, send-from and poll-inbox for `aria@perenniaai.com` |
| `backend/tasks/briefing_thread_tasks.py` | 4 Celery tasks: `poll_briefing_replies`, `process_briefing_reply`, `execute_briefing_tasks`, `expire_stale_threads` |
| `backend/routes/briefing_thread_routes.py` | API endpoints for thread status, admin review, manual retry |
| `backend/migrations/create_briefing_thread_tables.py` | DDL for new tables + indexes |

### New files (backend tests)

| File | Covers |
|------|--------|
| `backend/tests/test_briefing_thread_models.py` | Model instantiation, constraints, relationships |
| `backend/tests/test_briefing_thread_service.py` | State machine transitions, idempotency, loop cap |
| `backend/tests/test_briefing_reply_parser.py` | Quoted-reply stripping, ParsedReply extraction, edge cases |
| `backend/tests/test_briefing_executor.py` | Pre-flight validation, risk gating, tool dispatch |
| `backend/tests/test_briefing_audit_service.py` | Chained hashes, compliance flag detection |
| `backend/tests/test_briefing_thread_tasks.py` | Celery task dispatch, reply matching, expiry |

### New files (frontend)

| File | Responsibility |
|------|---------------|
| `frontend/src/components/briefing/BriefingErrorBoundary.js` | Error boundary wrapping MorningBriefingCard |
| `frontend/src/components/briefing/shared.js` | Extracted shared helpers: `healthLabel`, `formatVolume`, section components |

### Modified files

| File | Change |
|------|--------|
| `backend/agents/autonomous/morning_briefing.py` | **DELETE** (dead code, audit #1) |
| `backend/tasks/morning_briefing_tasks.py` | Fix DB session leaks (audit #3) |
| `backend/templates/morning_briefing_email.py` | Add `html.escape()` to all interpolated values (audit #2), add thread token to outbound briefing |
| `backend/database/models/__init__.py` | Import new models |
| `backend/tasks/celery_app.py` | Add 3 new Beat schedule entries |
| `backend/feature_tiers.py` | Add `interactive_briefing` module |
| `frontend/src/components/dashboard/MorningBriefingCard.js` | Fix UTC dismiss date (audit #5), unify status filter (audit #7) |
| `frontend/src/pages/BriefingPage.js` | Unify status filter (audit #7), import shared components (audit #4) |
| `frontend/src/pages/Dashboard.js` | Wrap MorningBriefingCard with error boundary (audit #6) |

---

## Phase 1: Audit Cleanup

### Task 1: Delete dead autonomous morning briefing code

**Files:**
- Delete: `backend/agents/autonomous/morning_briefing.py`

- [ ] **Step 1: Verify the file is truly dead**

```bash
grep -rn "morning_briefing" backend/agents/autonomous/ --include="*.py"
grep -rn "autonomous.morning_briefing\|from agents.autonomous.morning_briefing\|from agents.autonomous import morning_briefing" backend/ --include="*.py"
```

Expected: No imports found from any active code. The only references should be within the file itself.

- [ ] **Step 2: Delete the file**

```bash
rm backend/agents/autonomous/morning_briefing.py
```

- [ ] **Step 3: Verify no import errors**

```bash
cd backend && python -c "from tasks.morning_briefing_tasks import dispatch_briefings; print('OK')"
```

Expected: `OK` — the active task file doesn't import from the dead file.

- [ ] **Step 4: Commit**

```bash
git add -u backend/agents/autonomous/morning_briefing.py
git commit -m "fix: delete dead autonomous morning_briefing.py (no tenant isolation)"
```

---

### Task 2: Fix DB session leaks in morning_briefing_tasks.py

**Files:**
- Modify: `backend/tasks/morning_briefing_tasks.py`
- Test: `backend/tests/test_morning_briefing_tasks.py` (verify existing tests still pass)

- [ ] **Step 1: Read the current session management pattern**

Read `backend/tasks/morning_briefing_tasks.py` and identify every `SessionLocal()` call and its corresponding `.close()`. Look for paths where an exception could skip the `.close()`.

- [ ] **Step 2: Refactor to context managers**

Replace every bare `SessionLocal()` call with a context manager pattern. The pattern to apply:

In `_get_db_session()` or wherever sessions are created:

```python
from contextlib import contextmanager

@contextmanager
def _get_scoped_session(org_id=None):
    """Yield a DB session that always closes, with optional tenant scoping."""
    from db import SessionLocal
    db = SessionLocal()
    try:
        if org_id is not None:
            db.execute(text("SET app.current_tenant = :org_id"), {"org_id": str(org_id)})
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
```

Then replace all usage sites. For example, in `dispatch_briefings`:

```python
# BEFORE (leaky):
db = SessionLocal()
try:
    users = db.query(User).filter(...)
    # ... work ...
    db.close()
except Exception:
    db.close()

# AFTER (safe):
with _get_scoped_session() as db:
    users = db.query(User).filter(...)
    # ... work ...
```

Apply this pattern to every function that creates a session: `dispatch_briefings`, `generate_user_briefing`, `cleanup_old_briefings`, and any helper functions like `_get_tenant_db_session`.

- [ ] **Step 3: Run existing tests**

```bash
cd backend && python -m pytest tests/test_morning_briefing_tasks.py -v
```

Expected: All existing tests pass.

- [ ] **Step 4: Verify syntax**

```bash
cd backend && python -c "import py_compile; py_compile.compile('tasks/morning_briefing_tasks.py', doraise=True); print('OK')"
```

- [ ] **Step 5: Commit**

```bash
git add backend/tasks/morning_briefing_tasks.py
git commit -m "fix: DB session leaks in morning_briefing_tasks.py — use context managers"
```

---

### Task 3: Add html.escape() to morning briefing email template

**Files:**
- Modify: `backend/templates/morning_briefing_email.py`
- Test: `backend/tests/test_email_templates.py` (add XSS test)

- [ ] **Step 1: Write a failing test**

Add to `backend/tests/test_email_templates.py`:

```python
import html
from templates.morning_briefing_email import render_briefing_email

class TestBriefingEmailXSS:
    def test_borrower_name_is_escaped(self):
        """Borrower names from CRM must be HTML-escaped in the email."""
        malicious_name = '<script>alert("xss")</script>'
        at_risk = [{"borrower": malicious_name, "loan_number": "123", "stage": "PROCESSING", "days_in_stage": 5, "reason": "stalled"}]
        html_output = render_briefing_email(
            user_name="Test LO",
            briefing_date=date(2026, 5, 7),
            level="individual",
            ai_narrative="Test narrative.",
            pipeline={"active_count": 1, "total_volume": 100000, "closing_soon": 0, "by_stage": {}},
            at_risk=at_risk,
            stale_leads=[],
            appointments=[],
            conditions=[],
            yesterday={"funded": 0, "new_loans": 0, "conversions": 0},
            team=None,
        )
        assert malicious_name not in html_output
        assert html.escape(malicious_name) in html_output
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd backend && python -m pytest tests/test_email_templates.py::TestBriefingEmailXSS -v
```

Expected: FAIL — the malicious name appears unescaped.

- [ ] **Step 3: Add html.escape() to all interpolated values**

Read `backend/templates/morning_briefing_email.py`. Add `import html` at the top. Then in every section builder function (`_section_at_risk`, `_section_stale_leads`, `_section_appointments`, `_section_conditions`, `_section_team`, `_section_org`), wrap all data values in `html.escape(str(...))`:

```python
import html

def _esc(value):
    """HTML-escape a value for safe email rendering."""
    return html.escape(str(value)) if value is not None else ""
```

Apply `_esc()` to every f-string interpolation of data values: `{_esc(item["borrower"])}`, `{_esc(item["loan_number"])}`, `{_esc(item["name"])}`, etc. Do NOT escape the HTML structure itself (tags, CSS) — only data values that come from the database.

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd backend && python -m pytest tests/test_email_templates.py::TestBriefingEmailXSS -v
```

Expected: PASS

- [ ] **Step 5: Verify syntax**

```bash
cd backend && python -c "import py_compile; py_compile.compile('templates/morning_briefing_email.py', doraise=True); print('OK')"
```

- [ ] **Step 6: Commit**

```bash
git add backend/templates/morning_briefing_email.py backend/tests/test_email_templates.py
git commit -m "fix: html.escape() all interpolated values in briefing email template"
```

---

### Task 4: Add error boundary around MorningBriefingCard

**Files:**
- Create: `frontend/src/components/briefing/BriefingErrorBoundary.js`
- Modify: `frontend/src/pages/Dashboard.js`

- [ ] **Step 1: Create the error boundary component**

```javascript
// frontend/src/components/briefing/BriefingErrorBoundary.js
import React from 'react';

class BriefingErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error, errorInfo) {
    console.error('MorningBriefingCard crashed:', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return null;
    }
    return this.props.children;
  }
}

export default BriefingErrorBoundary;
```

- [ ] **Step 2: Wrap MorningBriefingCard in Dashboard.js**

In `frontend/src/pages/Dashboard.js`, add the import and wrap:

```javascript
import BriefingErrorBoundary from '../components/briefing/BriefingErrorBoundary';
```

Find the `<MorningBriefingCard />` usage (line ~1085) and wrap it:

```javascript
<BriefingErrorBoundary>
  <MorningBriefingCard />
</BriefingErrorBoundary>
```

- [ ] **Step 3: Verify the dev server renders the dashboard**

```bash
cd frontend && npm run dev
```

Open `http://localhost:5173/dashboard` in a browser. The dashboard should load with the briefing card visible (or no card if no briefing exists). No console errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/briefing/BriefingErrorBoundary.js frontend/src/pages/Dashboard.js
git commit -m "fix: add error boundary around MorningBriefingCard on Dashboard"
```

---

### Task 5: Fix UTC dismiss date in MorningBriefingCard

**Files:**
- Modify: `frontend/src/components/dashboard/MorningBriefingCard.js`

- [ ] **Step 1: Find the UTC bug**

Read `frontend/src/components/dashboard/MorningBriefingCard.js`. Search for `toISOString().split('T')[0]`. This produces a UTC date, not local. At 11 PM EST, `toISOString()` returns tomorrow's date in UTC.

- [ ] **Step 2: Replace with local date formatting**

Create a helper that returns local YYYY-MM-DD:

```javascript
function getLocalDateString() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}
```

Replace every instance of `new Date().toISOString().split('T')[0]` with `getLocalDateString()`. There should be 2 instances: one in the `useState` initializer and one in the `dismiss` handler.

- [ ] **Step 3: Verify in browser**

Open Dashboard. Dismiss the briefing card. Check localStorage: `briefing_dismissed_date` should show today's local date, not UTC.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/dashboard/MorningBriefingCard.js
git commit -m "fix: MorningBriefingCard dismiss date uses local timezone instead of UTC"
```

---

### Task 6: Unify status filtering between card and page

**Files:**
- Modify: `frontend/src/components/dashboard/MorningBriefingCard.js`
- Modify: `frontend/src/pages/BriefingPage.js`

- [ ] **Step 1: Identify the filtering mismatch**

Read both files and find status filtering:
- **Card** (`MorningBriefingCard.js`): Checks `res.data.status === 'delivered'` — only shows delivered briefings.
- **Page** (`BriefingPage.js`): No status check — shows any briefing data returned by the API.

The card is the correct behavior — a briefing should only be shown if its status is `'delivered'`. The page should also check.

- [ ] **Step 2: Add status check to BriefingPage.js**

In the `TodayTab` component's fetch handler (where it processes the API response from `/api/v1/briefing/today`), add the same guard:

```javascript
if (res.status === 200 && res.data && res.data.status === 'delivered') {
  setBriefing(res.data);
} else {
  setBriefing(null);
}
```

If the page currently shows a "generating" state differently, preserve that: show a "Briefing is being generated..." message when `res.data.status === 'generating'`, and show nothing for other states.

- [ ] **Step 3: Verify in browser**

Open `/briefing`. If a briefing exists for today, it should show. If no briefing or non-delivered status, the page should show an appropriate empty state.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/dashboard/MorningBriefingCard.js frontend/src/pages/BriefingPage.js
git commit -m "fix: unify status filtering between MorningBriefingCard and BriefingPage"
```

---

### Task 7: Extract shared briefing components

**Files:**
- Create: `frontend/src/components/briefing/shared.js`
- Modify: `frontend/src/pages/BriefingPage.js`
- Modify: `frontend/src/components/dashboard/MorningBriefingCard.js`

- [ ] **Step 1: Identify duplicated code**

Read both `BriefingPage.js` and `MorningBriefingCard.js`. Find functions and components that appear in both:
- `healthLabel(health)` — maps "green"/"yellow"/"red" to display labels
- `formatVolume(amount)` — formats dollar amounts
- Section rendering logic (at-risk items, stale leads, conditions, appointments)
- Health indicator dot component

- [ ] **Step 2: Create shared module**

Create `frontend/src/components/briefing/shared.js` with the extracted helpers:

```javascript
export function healthLabel(health) {
  // copy from BriefingPage.js — the canonical version
}

export function formatVolume(amount) {
  // copy from BriefingPage.js — the canonical version
}

export function HealthDot({ health }) {
  const colors = { green: '#10B981', yellow: '#F59E0B', red: '#EF4444' };
  return (
    <span style={{
      display: 'inline-block',
      width: 8,
      height: 8,
      borderRadius: '50%',
      backgroundColor: colors[health] || '#9CA3AF',
      marginRight: 6,
    }} />
  );
}
```

- [ ] **Step 3: Update BriefingPage.js to import from shared**

Replace the local definitions with imports:

```javascript
import { healthLabel, formatVolume, HealthDot } from '../components/briefing/shared';
```

Delete the local copies of these functions.

- [ ] **Step 4: Update MorningBriefingCard.js to import from shared**

```javascript
import { healthLabel, formatVolume, HealthDot } from '../briefing/shared';
```

Delete the local copies.

- [ ] **Step 5: Verify in browser**

Open both `/dashboard` (card) and `/briefing` (page). Both should render identically to before the refactor. Check console for errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/briefing/shared.js frontend/src/pages/BriefingPage.js frontend/src/components/dashboard/MorningBriefingCard.js
git commit -m "refactor: extract shared briefing components from BriefingPage and MorningBriefingCard"
```

---

## Phase 2: Data Layer

### Task 8: Create BriefingThread, BriefingTask, and BriefingAuditLog models

**Files:**
- Create: `backend/database/models/briefing_thread.py`
- Modify: `backend/database/models/__init__.py`
- Test: `backend/tests/test_briefing_thread_models.py`

- [ ] **Step 1: Write the model test**

Create `backend/tests/test_briefing_thread_models.py`:

```python
"""Tests for interactive briefing thread models."""
import pytest
import uuid
from datetime import datetime, date, timezone, timedelta
from unittest.mock import MagicMock
from database.models.briefing_thread import BriefingThread, BriefingTask, BriefingAuditLog


class TestBriefingThreadModel:
    def test_create_thread(self):
        thread = BriefingThread(
            organization_id=1,
            user_id=10,
            morning_briefing_id=100,
            thread_token=uuid.uuid4(),
            state="BRIEFING_SENT",
            trust_mode=3,
            loop_count=0,
            briefing_items=[{"item": 1, "summary": "Follow up with Torres"}],
            expires_at=datetime.now(timezone.utc) + timedelta(hours=4),
        )
        assert thread.state == "BRIEFING_SENT"
        assert thread.trust_mode == 3
        assert thread.loop_count == 0

    def test_thread_token_is_uuid(self):
        token = uuid.uuid4()
        thread = BriefingThread(thread_token=token)
        assert thread.thread_token == token

    def test_default_trust_mode(self):
        thread = BriefingThread()
        assert thread.trust_mode == 3


class TestBriefingTaskModel:
    def test_create_task(self):
        task = BriefingTask(
            thread_id=1,
            organization_id=1,
            briefing_item_number=1,
            briefing_item_summary="Send follow-up to Torres",
            action_type="send_borrower_email",
            action_params={"to": "torres@example.com", "template": "follow_up"},
            tool_name="send_email",
            confidence_score=0.95,
            risk_level="low",
            status="pending",
        )
        assert task.action_type == "send_borrower_email"
        assert task.status == "pending"

    def test_valid_statuses(self):
        for status in ["pending", "approved", "executing", "completed", "failed", "failed_preflight", "carryover"]:
            task = BriefingTask(status=status)
            assert task.status == status

    def test_idempotency_key_stored(self):
        task = BriefingTask(idempotency_key="bt_1_attempt_1")
        assert task.idempotency_key == "bt_1_attempt_1"


class TestBriefingAuditLogModel:
    def test_create_audit_entry(self):
        entry = BriefingAuditLog(
            organization_id=1,
            thread_id=1,
            event_type="state_transition",
            actor="system",
            payload={"from": "BRIEFING_SENT", "to": "AWAITING_REPLY"},
            payload_hash="abc123",
            prev_hash="000000",
        )
        assert entry.event_type == "state_transition"
        assert entry.actor == "system"
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd backend && python -m pytest tests/test_briefing_thread_models.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'database.models.briefing_thread'`

- [ ] **Step 3: Create the model file**

Create `backend/database/models/briefing_thread.py`:

```python
"""Interactive briefing thread models — V1 conversation loop.

Spec: docs/superpowers/specs/2026-05-07-interactive-morning-briefing-design.md
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, BigInteger, String, Text, Float, Date,
    DateTime, ForeignKey, Index, UniqueConstraint, Boolean,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from db import Base


class BriefingThread(Base):
    __tablename__ = "briefing_threads"

    id = Column(Integer, primary_key=True, autoincrement=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    morning_briefing_id = Column(Integer, ForeignKey("morning_briefings.id"), nullable=True)
    thread_token = Column(UUID(as_uuid=True), default=uuid.uuid4, unique=True, nullable=False)
    outbound_message_id = Column(String(512), nullable=True)
    state = Column(String(50), nullable=False, default="BRIEFING_SENT")
    trust_mode = Column(Integer, nullable=False, default=3)
    loop_count = Column(Integer, nullable=False, default=0)
    briefing_items = Column(JSONB, nullable=True)
    extracted_tasks = Column(JSONB, nullable=True)
    lo_reply_raw = Column(Text, nullable=True)
    lo_approval_raw = Column(Text, nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    tasks = relationship("BriefingTask", back_populates="thread", cascade="all, delete-orphan")
    audit_entries = relationship("BriefingAuditLog", back_populates="thread", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_bt_org_user_state", "organization_id", "user_id", "state"),
        Index("ix_bt_org_expires", "organization_id", "expires_at",
              postgresql_where="state IN ('AWAITING_REPLY', 'AWAITING_APPROVAL')"),
        Index("ix_bt_outbound_msg", "outbound_message_id"),
    )


class BriefingTask(Base):
    __tablename__ = "briefing_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    thread_id = Column(Integer, ForeignKey("briefing_threads.id"), nullable=False)
    organization_id = Column(Integer, nullable=False, index=True)
    briefing_item_number = Column(Integer, nullable=False)
    briefing_item_summary = Column(Text, nullable=True)
    action_type = Column(String(50), nullable=False)
    action_params = Column(JSONB, nullable=True)
    tool_name = Column(String(100), nullable=True)
    lo_override_notes = Column(Text, nullable=True)
    confidence_score = Column(Float, nullable=True)
    risk_level = Column(String(20), nullable=True, default="low")
    preflight_result = Column(JSONB, nullable=True)
    idempotency_key = Column(String(255), unique=True, nullable=True)
    status = Column(String(30), nullable=False, default="pending")
    carryover_target_date = Column(Date, nullable=True)
    result_data = Column(JSONB, nullable=True)
    error_message = Column(Text, nullable=True)
    executed_at = Column(DateTime(timezone=True), nullable=True)

    thread = relationship("BriefingThread", back_populates="tasks")

    __table_args__ = (
        Index("ix_btask_thread_status", "thread_id", "status"),
        Index("ix_btask_org", "organization_id"),
    )


class BriefingAuditLog(Base):
    __tablename__ = "briefing_audit_log"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    organization_id = Column(Integer, nullable=False, index=True)
    thread_id = Column(Integer, ForeignKey("briefing_threads.id"), nullable=False)
    task_id = Column(Integer, ForeignKey("briefing_tasks.id"), nullable=True)
    event_type = Column(String(50), nullable=False)
    actor = Column(String(100), nullable=False)
    payload = Column(JSONB, nullable=True)
    payload_hash = Column(String(64), nullable=True)
    prev_hash = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)

    thread = relationship("BriefingThread", back_populates="audit_entries")

    __table_args__ = (
        Index("ix_bal_org_created", "organization_id", "created_at"),
    )
```

- [ ] **Step 4: Register in models/__init__.py**

Add to `backend/database/models/__init__.py`:

```python
from database.models.briefing_thread import BriefingThread, BriefingTask, BriefingAuditLog
```

- [ ] **Step 5: Run the test**

```bash
cd backend && python -m pytest tests/test_briefing_thread_models.py -v
```

Expected: PASS

- [ ] **Step 6: Verify the full model import chain**

```bash
cd backend && python -c "from database.models import BriefingThread, BriefingTask, BriefingAuditLog; print('Models:', BriefingThread.__tablename__, BriefingTask.__tablename__, BriefingAuditLog.__tablename__)"
```

Expected: `Models: briefing_threads briefing_tasks briefing_audit_log`

- [ ] **Step 7: Commit**

```bash
git add backend/database/models/briefing_thread.py backend/database/models/__init__.py backend/tests/test_briefing_thread_models.py
git commit -m "feat: BriefingThread, BriefingTask, BriefingAuditLog models"
```

---

### Task 9: Create Pydantic schemas for reply parsing

**Files:**
- Create: `backend/schemas/briefing_thread.py`
- Test: `backend/tests/test_briefing_reply_parser.py` (schema validation tests only)

- [ ] **Step 1: Write schema validation tests**

Create the test file (schema portion only — parser tests come in Task 14):

```python
"""Tests for briefing thread schemas and reply parsing."""
import pytest
from schemas.briefing_thread import (
    ParsedReply, ItemOverride, BulkAction,
    BriefingThreadResponse, BriefingTaskResponse,
)


class TestParsedReplySchema:
    def test_basic_parsed_reply(self):
        reply = ParsedReply(
            handled_items=[1, 3, 5],
            skipped_items=[2],
            overrides=[],
            bulk_action=None,
            free_text_instructions=[],
            confidence=0.95,
            requires_clarification=False,
            clarification_question=None,
        )
        assert reply.handled_items == [1, 3, 5]
        assert reply.confidence == 0.95

    def test_bulk_action_handle_all(self):
        reply = ParsedReply(
            handled_items=[],
            skipped_items=[],
            overrides=[],
            bulk_action=BulkAction(type="handle_all", except_items=[]),
            free_text_instructions=[],
            confidence=0.92,
            requires_clarification=False,
            clarification_question=None,
        )
        assert reply.bulk_action.type == "handle_all"

    def test_override_with_validation(self):
        override = ItemOverride(
            item_number=3,
            new_action_type="schedule_call",
            instruction_delta="call instead of email",
            requires_validation=["phone_number_on_file", "calendar_availability"],
        )
        assert override.new_action_type == "schedule_call"
        assert len(override.requires_validation) == 2

    def test_low_confidence_triggers_clarification(self):
        reply = ParsedReply(
            handled_items=[1],
            skipped_items=[],
            overrides=[],
            bulk_action=None,
            free_text_instructions=["also remind me to call the underwriter"],
            confidence=0.45,
            requires_clarification=True,
            clarification_question="Did you want me to handle item 1 only?",
        )
        assert reply.requires_clarification is True
        assert reply.clarification_question is not None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/test_briefing_reply_parser.py::TestParsedReplySchema -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'schemas.briefing_thread'`

- [ ] **Step 3: Create the schemas file**

Create `backend/schemas/briefing_thread.py`:

```python
"""Pydantic schemas for the interactive briefing thread system."""
from __future__ import annotations
from datetime import datetime, date
from typing import Optional
from pydantic import BaseModel, Field
from enum import Enum


# --- Reply Parsing (Claude structured output) ---

class BulkAction(BaseModel):
    type: str = Field(description="'handle_all' or 'handle_except'")
    except_items: list[int] = Field(default_factory=list)


class ItemOverride(BaseModel):
    item_number: int
    new_action_type: Optional[str] = None
    instruction_delta: str = ""
    requires_validation: list[str] = Field(default_factory=list)


class ParsedReply(BaseModel):
    handled_items: list[int] = Field(default_factory=list)
    skipped_items: list[int] = Field(default_factory=list)
    overrides: list[ItemOverride] = Field(default_factory=list)
    bulk_action: Optional[BulkAction] = None
    free_text_instructions: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    requires_clarification: bool = False
    clarification_question: Optional[str] = None


# --- Approval Classification ---

class ApprovalIntent(str, Enum):
    APPROVE = "approve"
    APPROVE_ALL = "approve_all"
    APPROVE_SPECIFIC = "approve_specific"
    APPROVE_EXCEPT = "approve_except"
    MODIFY = "modify"
    CANCEL = "cancel"


class ClassifiedApproval(BaseModel):
    intent: ApprovalIntent
    task_numbers: list[int] = Field(default_factory=list)
    modification_text: Optional[str] = None


# --- Thread States ---

VALID_STATES = {
    "BRIEFING_SENT", "AWAITING_REPLY", "PARSING_INSTRUCTIONS",
    "CONFIRMATION_SENT", "AWAITING_APPROVAL", "EXECUTING",
    "RESULTS_SENT", "EXPIRED", "CANCELLED", "FAILED",
    "MANUAL_REVIEW", "CLARIFICATION_SENT",
}

TERMINAL_STATES = {"RESULTS_SENT", "EXPIRED", "CANCELLED", "FAILED", "MANUAL_REVIEW"}

VALID_TRANSITIONS = {
    "BRIEFING_SENT": {"AWAITING_REPLY"},
    "AWAITING_REPLY": {"PARSING_INSTRUCTIONS", "EXPIRED"},
    "PARSING_INSTRUCTIONS": {"CONFIRMATION_SENT", "CLARIFICATION_SENT", "MANUAL_REVIEW"},
    "CONFIRMATION_SENT": {"AWAITING_APPROVAL"},
    "AWAITING_APPROVAL": {"EXECUTING", "CONFIRMATION_SENT", "CANCELLED", "EXPIRED"},
    "CLARIFICATION_SENT": {"AWAITING_REPLY"},
    "EXECUTING": {"RESULTS_SENT", "FAILED"},
}


# --- Supported Action Types ---

SUPPORTED_ACTION_TYPES = {
    "send_borrower_email",
    "send_realtor_update",
    "create_crm_task",
    "schedule_call",
    "assign_processor_task",
    "request_docs",
    "update_pipeline_stage",
    "send_checklist",
}

ACTION_TOOL_MAP = {
    "send_borrower_email": "send_email",
    "send_realtor_update": "send_email",
    "create_crm_task": "create_task",
    "schedule_call": "book_appointment",
    "assign_processor_task": "assign_task",
    "request_docs": "track_document_request",
    "update_pipeline_stage": "update_loan_fields",
    "send_checklist": "send_email",
}

HIGH_RISK_ACTIONS = {"update_pipeline_stage"}


# --- API Response Schemas ---

class BriefingTaskResponse(BaseModel):
    id: int
    briefing_item_number: int
    briefing_item_summary: Optional[str] = None
    action_type: str
    tool_name: Optional[str] = None
    confidence_score: Optional[float] = None
    risk_level: Optional[str] = None
    status: str
    result_data: Optional[dict] = None
    error_message: Optional[str] = None
    executed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class BriefingThreadResponse(BaseModel):
    id: int
    thread_token: str
    state: str
    trust_mode: int
    loop_count: int
    briefing_items: Optional[list] = None
    extracted_tasks: Optional[list] = None
    expires_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    tasks: list[BriefingTaskResponse] = Field(default_factory=list)

    model_config = {"from_attributes": True}
```

- [ ] **Step 4: Run the tests**

```bash
cd backend && python -m pytest tests/test_briefing_reply_parser.py::TestParsedReplySchema -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/schemas/briefing_thread.py backend/tests/test_briefing_reply_parser.py
git commit -m "feat: Pydantic schemas for briefing thread system (ParsedReply, state machine, action types)"
```

---

### Task 10: Create migration script for new tables

**Files:**
- Create: `backend/migrations/create_briefing_thread_tables.py`

- [ ] **Step 1: Write the migration script**

Create `backend/migrations/create_briefing_thread_tables.py`:

```python
"""Create briefing_threads, briefing_tasks, and briefing_audit_log tables.

Run: python migrations/create_briefing_thread_tables.py
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text, inspect
from db import Base

# Import models to register them on Base.metadata
from database.models.briefing_thread import BriefingThread, BriefingTask, BriefingAuditLog


def run_migration():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL not set")
        sys.exit(1)

    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    engine = create_engine(database_url)
    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()

    tables = [
        BriefingThread.__table__,
        BriefingTask.__table__,
        BriefingAuditLog.__table__,
    ]

    for table in tables:
        if table.name in existing_tables:
            print(f"  Table '{table.name}' already exists, skipping.")
        else:
            table.create(engine, checkfirst=True)
            print(f"  Created table '{table.name}'.")

    # Verify indexes
    for table in tables:
        indexes = inspector.get_indexes(table.name)
        print(f"  {table.name}: {len(indexes)} indexes")

    print("Migration complete.")


if __name__ == "__main__":
    run_migration()
```

- [ ] **Step 2: Verify syntax**

```bash
cd backend && python -c "import py_compile; py_compile.compile('migrations/create_briefing_thread_tables.py', doraise=True); print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add backend/migrations/create_briefing_thread_tables.py
git commit -m "feat: migration script for briefing_threads, briefing_tasks, briefing_audit_log"
```

---

## Phase 3: Core Services

### Task 11: Create briefing audit service (chained hashes)

**Files:**
- Create: `backend/services/briefing_audit_service.py`
- Test: `backend/tests/test_briefing_audit_service.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_briefing_audit_service.py`:

```python
"""Tests for briefing audit service — chained hash integrity."""
import pytest
import hashlib
import json
from unittest.mock import MagicMock, patch
from services.briefing_audit_service import BriefingAuditService


class TestChainedHashing:
    def test_first_entry_uses_zero_prev_hash(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
        service = BriefingAuditService(db, organization_id=1)
        entry = service.log_event(
            thread_id=1,
            event_type="state_transition",
            actor="system",
            payload={"from": "BRIEFING_SENT", "to": "AWAITING_REPLY"},
        )
        assert entry.prev_hash == "0" * 64

    def test_second_entry_chains_from_first(self):
        db = MagicMock()
        first_entry = MagicMock()
        first_entry.payload_hash = "abc123def456"
        db.query.return_value.filter.return_value.order_by.return_value.first.return_value = first_entry

        service = BriefingAuditService(db, organization_id=1)
        entry = service.log_event(
            thread_id=1,
            event_type="tool_call",
            actor="aria",
            payload={"tool": "send_email", "params": {"to": "test@example.com"}},
        )
        assert entry.prev_hash == "abc123def456"

    def test_payload_hash_is_sha256(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
        service = BriefingAuditService(db, organization_id=1)
        payload = {"test": "data"}
        entry = service.log_event(
            thread_id=1,
            event_type="state_transition",
            actor="system",
            payload=payload,
        )
        expected_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
        assert entry.payload_hash == expected_hash

    def test_pii_redacted_in_stored_payload(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
        service = BriefingAuditService(db, organization_id=1)
        payload = {"borrower_ssn": "123-45-6789", "name": "John"}
        entry = service.log_event(
            thread_id=1,
            event_type="tool_call",
            actor="aria",
            payload=payload,
        )
        # SSN should be redacted in stored payload
        assert "123-45-6789" not in json.dumps(entry.payload)
        # But hash is computed on un-redacted payload
        expected_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
        assert entry.payload_hash == expected_hash


class TestComplianceFlags:
    def test_tcpa_optout_detected(self):
        db = MagicMock()
        service = BriefingAuditService(db, organization_id=1)
        flags = service.check_compliance_flags(
            action_type="send_borrower_email",
            action_params={"borrower_id": 1},
            borrower_record=MagicMock(tcpa_opt_out=True),
            loan_record=None,
        )
        assert "tcpa_optout_violation_blocked" in [f["flag"] for f in flags]

    def test_no_flags_on_clean_action(self):
        db = MagicMock()
        service = BriefingAuditService(db, organization_id=1)
        flags = service.check_compliance_flags(
            action_type="create_crm_task",
            action_params={},
            borrower_record=MagicMock(tcpa_opt_out=False),
            loan_record=None,
        )
        assert len(flags) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && python -m pytest tests/test_briefing_audit_service.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement the audit service**

Create `backend/services/briefing_audit_service.py`:

```python
"""Briefing audit service — chained-hash audit log for SOC 2 compliance.

Every state transition, tool call, and email is logged with a SHA-256 hash
chain. The hash is computed on the un-redacted payload; the stored payload
is PII-redacted.
"""
import hashlib
import json
import re
import logging
from datetime import datetime, timezone
from typing import Optional, Any
from sqlalchemy.orm import Session
from database.models.briefing_thread import BriefingAuditLog

logger = logging.getLogger(__name__)

SSN_PATTERN = re.compile(r'\b\d{3}-\d{2}-\d{4}\b')
ACCOUNT_PATTERN = re.compile(r'\b\d{8,17}\b')
DOB_PATTERN = re.compile(r'\b\d{2}/\d{2}/\d{4}\b')


def _redact_pii(payload: dict) -> dict:
    """Redact SSN, DOB, and account numbers from payload values."""
    redacted = {}
    for key, value in payload.items():
        if isinstance(value, str):
            v = SSN_PATTERN.sub("***-**-****", value)
            v = DOB_PATTERN.sub("**/****/****", v)
            if "ssn" in key.lower() or "account" in key.lower():
                v = ACCOUNT_PATTERN.sub("****", v)
            redacted[key] = v
        elif isinstance(value, dict):
            redacted[key] = _redact_pii(value)
        else:
            redacted[key] = value
    return redacted


def _compute_hash(payload: dict) -> str:
    """SHA-256 hash of the un-redacted payload."""
    canonical = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


class BriefingAuditService:
    def __init__(self, db: Session, organization_id: int):
        self.db = db
        self.organization_id = organization_id

    def log_event(
        self,
        thread_id: int,
        event_type: str,
        actor: str,
        payload: dict,
        task_id: Optional[int] = None,
    ) -> BriefingAuditLog:
        payload_hash = _compute_hash(payload)

        prev_entry = (
            self.db.query(BriefingAuditLog)
            .filter(
                BriefingAuditLog.thread_id == thread_id,
                BriefingAuditLog.organization_id == self.organization_id,
            )
            .order_by(BriefingAuditLog.id.desc())
            .first()
        )
        prev_hash = prev_entry.payload_hash if prev_entry else "0" * 64

        redacted_payload = _redact_pii(payload)

        entry = BriefingAuditLog(
            organization_id=self.organization_id,
            thread_id=thread_id,
            task_id=task_id,
            event_type=event_type,
            actor=actor,
            payload=redacted_payload,
            payload_hash=payload_hash,
            prev_hash=prev_hash,
        )
        self.db.add(entry)
        self.db.flush()
        return entry

    def check_compliance_flags(
        self,
        action_type: str,
        action_params: dict,
        borrower_record: Any,
        loan_record: Any,
    ) -> list[dict]:
        flags = []

        if borrower_record and getattr(borrower_record, "tcpa_opt_out", False):
            if action_type in ("send_borrower_email", "send_checklist", "schedule_call"):
                flags.append({
                    "flag": "tcpa_optout_violation_blocked",
                    "blocking": True,
                    "detail": "Borrower has opted out of contact (TCPA).",
                })

        if action_type == "request_docs" and action_params.get("glba_sensitive"):
            flags.append({
                "flag": "glbasensitive_doc_request",
                "blocking": False,
                "detail": "Document request includes GLBA-flagged category.",
            })

        if action_type == "update_pipeline_stage" and loan_record:
            trid_stages = {"DISCLOSED", "CLOSING", "DOCS", "DOCS_OUT"}
            new_stage = action_params.get("stage", "")
            if new_stage in trid_stages:
                flags.append({
                    "flag": "trid_clock_change",
                    "blocking": False,
                    "detail": f"Stage transition to {new_stage} may alter TRID-tracked timestamps.",
                })

        return flags
```

- [ ] **Step 4: Run tests**

```bash
cd backend && python -m pytest tests/test_briefing_audit_service.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/briefing_audit_service.py backend/tests/test_briefing_audit_service.py
git commit -m "feat: briefing audit service with chained SHA-256 hashes and compliance flags"
```

---

### Task 12: Create state machine + thread service

**Files:**
- Create: `backend/services/briefing_thread_service.py`
- Test: `backend/tests/test_briefing_thread_service.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_briefing_thread_service.py`:

```python
"""Tests for briefing thread state machine."""
import pytest
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch
from services.briefing_thread_service import BriefingThreadService
from schemas.briefing_thread import TERMINAL_STATES


class TestStateTransitions:
    def setup_method(self):
        self.db = MagicMock()
        self.service = BriefingThreadService(self.db, organization_id=1)

    def test_valid_transition_briefing_sent_to_awaiting(self):
        thread = MagicMock(state="BRIEFING_SENT", organization_id=1)
        self.service.transition(thread, "AWAITING_REPLY")
        assert thread.state == "AWAITING_REPLY"

    def test_invalid_transition_raises(self):
        thread = MagicMock(state="BRIEFING_SENT", organization_id=1)
        with pytest.raises(ValueError, match="Invalid transition"):
            self.service.transition(thread, "EXECUTING")

    def test_terminal_state_blocks_transition(self):
        for state in TERMINAL_STATES:
            thread = MagicMock(state=state, organization_id=1)
            with pytest.raises(ValueError, match="terminal"):
                self.service.transition(thread, "AWAITING_REPLY")

    def test_modification_increments_loop_count(self):
        thread = MagicMock(state="AWAITING_APPROVAL", loop_count=0, organization_id=1)
        self.service.transition(thread, "CONFIRMATION_SENT")
        assert thread.loop_count == 1

    def test_loop_cap_at_3_escalates_to_manual_review(self):
        thread = MagicMock(state="AWAITING_APPROVAL", loop_count=3, organization_id=1)
        self.service.transition(thread, "CONFIRMATION_SENT")
        assert thread.state == "MANUAL_REVIEW"


class TestThreadCreation:
    def setup_method(self):
        self.db = MagicMock()
        self.service = BriefingThreadService(self.db, organization_id=1)

    def test_create_thread_sets_expiry(self):
        thread = self.service.create_thread(
            user_id=10,
            morning_briefing_id=100,
            briefing_items=[{"item": 1}],
        )
        assert thread.state == "BRIEFING_SENT"
        assert thread.trust_mode == 3
        assert thread.expires_at is not None
        delta = thread.expires_at - datetime.now(timezone.utc)
        assert timedelta(hours=3, minutes=50) < delta < timedelta(hours=4, minutes=10)


class TestIdempotency:
    def setup_method(self):
        self.db = MagicMock()
        self.service = BriefingThreadService(self.db, organization_id=1)

    def test_duplicate_reply_is_rejected(self):
        thread = MagicMock(state="AWAITING_REPLY", organization_id=1)
        # First call should succeed
        self.service.record_inbound_message(thread, message_id="msg_123", body="handle 1 and 3")
        # Second call with same message_id should be rejected
        from sqlalchemy.exc import IntegrityError
        self.db.flush.side_effect = IntegrityError("duplicate", {}, None)
        result = self.service.record_inbound_message(thread, message_id="msg_123", body="handle 1 and 3")
        assert result is None  # Duplicate detected
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && python -m pytest tests/test_briefing_thread_service.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement the thread service**

Create `backend/services/briefing_thread_service.py`:

```python
"""Briefing thread lifecycle and state machine.

Enforces valid transitions, idempotency guards, loop cap, and tenant isolation.
"""
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from database.models.briefing_thread import BriefingThread, BriefingTask
from schemas.briefing_thread import VALID_TRANSITIONS, TERMINAL_STATES
from services.briefing_audit_service import BriefingAuditService

logger = logging.getLogger(__name__)

LOOP_CAP = 3
EXPIRY_HOURS = 4


class BriefingThreadService:
    def __init__(self, db: Session, organization_id: int):
        self.db = db
        self.organization_id = organization_id
        self.audit = BriefingAuditService(db, organization_id)

    def create_thread(
        self,
        user_id: int,
        morning_briefing_id: int,
        briefing_items: list[dict],
    ) -> BriefingThread:
        now = datetime.now(timezone.utc)
        thread = BriefingThread(
            organization_id=self.organization_id,
            user_id=user_id,
            morning_briefing_id=morning_briefing_id,
            thread_token=uuid.uuid4(),
            state="BRIEFING_SENT",
            trust_mode=3,
            loop_count=0,
            briefing_items=briefing_items,
            expires_at=now + timedelta(hours=EXPIRY_HOURS),
        )
        self.db.add(thread)
        self.db.flush()

        self.audit.log_event(
            thread_id=thread.id,
            event_type="state_transition",
            actor="system",
            payload={"to": "BRIEFING_SENT"},
        )
        return thread

    def transition(self, thread: BriefingThread, new_state: str) -> None:
        if thread.organization_id != self.organization_id:
            from exceptions import TenantIsolationError
            raise TenantIsolationError(
                requesting_org_id=self.organization_id,
                target_org_id=thread.organization_id,
            )

        old_state = thread.state

        if old_state in TERMINAL_STATES:
            raise ValueError(f"Cannot transition from terminal state '{old_state}'")

        if old_state == "AWAITING_APPROVAL" and new_state == "CONFIRMATION_SENT":
            if thread.loop_count >= LOOP_CAP:
                thread.state = "MANUAL_REVIEW"
                thread.updated_at = datetime.now(timezone.utc)
                self.audit.log_event(
                    thread_id=thread.id,
                    event_type="state_transition",
                    actor="system",
                    payload={"from": old_state, "to": "MANUAL_REVIEW", "reason": "loop_cap_exceeded"},
                )
                return
            thread.loop_count += 1

        valid_next = VALID_TRANSITIONS.get(old_state, set())
        if new_state not in valid_next:
            raise ValueError(
                f"Invalid transition: '{old_state}' → '{new_state}'. "
                f"Valid: {valid_next}"
            )

        thread.state = new_state
        thread.updated_at = datetime.now(timezone.utc)

        self.audit.log_event(
            thread_id=thread.id,
            event_type="state_transition",
            actor="system",
            payload={"from": old_state, "to": new_state},
        )

    def record_inbound_message(
        self,
        thread: BriefingThread,
        message_id: str,
        body: str,
    ) -> Optional[str]:
        """Record an inbound reply. Returns body or None if duplicate."""
        try:
            if thread.state in ("AWAITING_REPLY", "CLARIFICATION_SENT"):
                thread.lo_reply_raw = body
            elif thread.state == "AWAITING_APPROVAL":
                thread.lo_approval_raw = body
            self.db.flush()
            return body
        except IntegrityError:
            self.db.rollback()
            logger.warning("Duplicate inbound message %s on thread %s", message_id, thread.id)
            return None

    def get_active_thread_for_user(self, user_id: int) -> Optional[BriefingThread]:
        return (
            self.db.query(BriefingThread)
            .filter(
                BriefingThread.organization_id == self.organization_id,
                BriefingThread.user_id == user_id,
                BriefingThread.state.notin_(list(TERMINAL_STATES)),
            )
            .order_by(BriefingThread.created_at.desc())
            .first()
        )

    def expire_stale_threads(self) -> int:
        now = datetime.now(timezone.utc)
        threads = (
            self.db.query(BriefingThread)
            .filter(
                BriefingThread.organization_id == self.organization_id,
                BriefingThread.expires_at <= now,
                BriefingThread.state.in_(["AWAITING_REPLY", "AWAITING_APPROVAL"]),
            )
            .all()
        )
        for thread in threads:
            thread.state = "EXPIRED"
            thread.updated_at = now
            self.audit.log_event(
                thread_id=thread.id,
                event_type="state_transition",
                actor="system",
                payload={"from": thread.state, "to": "EXPIRED", "reason": "4h_expiry"},
            )
        return len(threads)
```

- [ ] **Step 4: Run tests**

```bash
cd backend && python -m pytest tests/test_briefing_thread_service.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/briefing_thread_service.py backend/tests/test_briefing_thread_service.py
git commit -m "feat: briefing thread state machine with loop cap, idempotency, expiry"
```

---

### Task 13: Create reply parser (quoted-reply stripping + Claude extraction)

**Files:**
- Create: `backend/services/briefing_reply_parser.py`
- Test: `backend/tests/test_briefing_reply_parser.py` (add parser tests to existing file)

- [ ] **Step 1: Add parser tests to the existing test file**

Append to `backend/tests/test_briefing_reply_parser.py`:

```python
from services.briefing_reply_parser import strip_quoted_reply, parse_lo_reply


class TestQuotedReplyStripping:
    def test_strips_outlook_quote(self):
        raw = "Handle 1, 3, and 5\n\nOn May 7, 2026, Aria wrote:\n> Your morning briefing..."
        assert strip_quoted_reply(raw) == "Handle 1, 3, and 5"

    def test_strips_gmail_quote_markers(self):
        raw = "Do everything except 2\n\n> From: Aria\n> Subject: Morning Briefing"
        assert strip_quoted_reply(raw) == "Do everything except 2"

    def test_strips_gmail_html_blockquote(self):
        raw = 'Yes, handle all<div class="gmail_quote"><blockquote class="gmail_quote">Previous...</blockquote></div>'
        assert strip_quoted_reply(raw).strip() == "Yes, handle all"

    def test_empty_after_strip_returns_empty(self):
        raw = "On May 7, 2026, Aria wrote:\n> Your morning briefing..."
        assert strip_quoted_reply(raw) == ""

    def test_preserves_reply_with_no_quotes(self):
        raw = "Handle items 1 through 4, skip 5"
        assert strip_quoted_reply(raw) == "Handle items 1 through 4, skip 5"

    def test_strips_image_signature(self):
        raw = "approved\n\n[image: Company Logo]\nSent from my iPhone"
        result = strip_quoted_reply(raw)
        assert "approved" in result


class TestApprovalClassification:
    def test_approve_variants(self):
        from services.briefing_reply_parser import classify_approval
        for text in ["approved", "Approved", "APPROVED", "yes proceed", "go", "do it", "looks good"]:
            result = classify_approval(text)
            assert result.intent.value in ("approve", "approve_all"), f"Failed on: {text}"

    def test_approve_all(self):
        from services.briefing_reply_parser import classify_approval
        result = classify_approval("approve all")
        assert result.intent.value == "approve_all"

    def test_approve_specific(self):
        from services.briefing_reply_parser import classify_approval
        result = classify_approval("approve 1, 3, 5")
        assert result.intent.value == "approve_specific"
        assert result.task_numbers == [1, 3, 5]

    def test_approve_except(self):
        from services.briefing_reply_parser import classify_approval
        result = classify_approval("approve except 2")
        assert result.intent.value == "approve_except"
        assert result.task_numbers == [2]

    def test_cancel(self):
        from services.briefing_reply_parser import classify_approval
        for text in ["cancel", "nevermind", "stop"]:
            result = classify_approval(text)
            assert result.intent.value == "cancel", f"Failed on: {text}"

    def test_modification_fallback(self):
        from services.briefing_reply_parser import classify_approval
        result = classify_approval("Change item 2 to email instead of call")
        assert result.intent.value == "modify"
        assert result.modification_text is not None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && python -m pytest tests/test_briefing_reply_parser.py::TestQuotedReplyStripping -v
cd backend && python -m pytest tests/test_briefing_reply_parser.py::TestApprovalClassification -v
```

Expected: FAIL — `ModuleNotFoundError` for `briefing_reply_parser`

- [ ] **Step 3: Implement the reply parser**

Create `backend/services/briefing_reply_parser.py`:

```python
"""Reply parser — strips quoted content, classifies approvals, extracts tasks via Claude.

Quoted-reply stripping is deterministic Python. Task extraction calls Claude Haiku
with structured output (ParsedReply Pydantic model).
"""
import re
import logging
from typing import Optional
from schemas.briefing_thread import ParsedReply, ClassifiedApproval, ApprovalIntent

logger = logging.getLogger(__name__)

# Quoted-reply patterns
OUTLOOK_QUOTE = re.compile(r'^On .+wrote:\s*$', re.MULTILINE)
QUOTE_MARKER = re.compile(r'^>.*$', re.MULTILINE)
GMAIL_BLOCKQUOTE = re.compile(r'<(div|blockquote)\s+class="gmail_quote".*', re.DOTALL | re.IGNORECASE)
IMAGE_SIG = re.compile(r'\[image:.*?\].*$', re.DOTALL | re.MULTILINE)
SENT_FROM = re.compile(r'^Sent from my .*$', re.MULTILINE | re.IGNORECASE)

# Approval patterns
APPROVE_PATTERNS = re.compile(
    r'^(approved?|yes\s*proceed|go|do\s*it|looks?\s*good|lgtm|yes|yep|👍)\s*[.!]?\s*$',
    re.IGNORECASE,
)
APPROVE_ALL = re.compile(r'^approve\s*all\s*[.!]?\s*$', re.IGNORECASE)
APPROVE_SPECIFIC = re.compile(r'^approve\s+([\d,\s]+)\s*$', re.IGNORECASE)
APPROVE_EXCEPT = re.compile(r'^approve\s+except\s+([\d,\s]+)\s*$', re.IGNORECASE)
CANCEL_PATTERNS = re.compile(r'^(cancel|nevermind|never\s*mind|stop|abort)\s*[.!]?\s*$', re.IGNORECASE)


def strip_quoted_reply(raw: str) -> str:
    """Remove quoted previous messages, signatures, and boilerplate."""
    text = raw

    # 1. Strip Gmail HTML blockquotes
    text = GMAIL_BLOCKQUOTE.sub('', text)

    # 2. Strip everything below "On <date>, ... wrote:" line
    match = OUTLOOK_QUOTE.search(text)
    if match:
        text = text[:match.start()]

    # 3. Strip lines starting with >
    text = QUOTE_MARKER.sub('', text)

    # 4. Strip image signatures and "Sent from" lines
    text = IMAGE_SIG.sub('', text)
    text = SENT_FROM.sub('', text)

    return text.strip()


def classify_approval(text: str) -> ClassifiedApproval:
    """Classify a reply as approval, modification, or cancellation. Deterministic regex."""
    text = text.strip()

    if CANCEL_PATTERNS.match(text):
        return ClassifiedApproval(intent=ApprovalIntent.CANCEL)

    if APPROVE_ALL.match(text):
        return ClassifiedApproval(intent=ApprovalIntent.APPROVE_ALL)

    m = APPROVE_EXCEPT.match(text)
    if m:
        nums = [int(n.strip()) for n in m.group(1).split(',') if n.strip().isdigit()]
        return ClassifiedApproval(intent=ApprovalIntent.APPROVE_EXCEPT, task_numbers=nums)

    m = APPROVE_SPECIFIC.match(text)
    if m:
        nums = [int(n.strip()) for n in m.group(1).split(',') if n.strip().isdigit()]
        return ClassifiedApproval(intent=ApprovalIntent.APPROVE_SPECIFIC, task_numbers=nums)

    if APPROVE_PATTERNS.match(text):
        return ClassifiedApproval(intent=ApprovalIntent.APPROVE)

    return ClassifiedApproval(intent=ApprovalIntent.MODIFY, modification_text=text)


async def parse_lo_reply(
    reply_text: str,
    briefing_items: list[dict],
    anthropic_client=None,
) -> ParsedReply:
    """Call Claude Haiku to extract structured tasks from the LO's natural language reply.

    Args:
        reply_text: The LO's reply after quoted-reply stripping.
        briefing_items: The numbered briefing items the LO saw.
        anthropic_client: Anthropic async client. If None, creates one.
    """
    if not reply_text.strip():
        return ParsedReply(
            handled_items=[],
            skipped_items=[],
            overrides=[],
            confidence=0.0,
            requires_clarification=True,
            clarification_question="Your reply appeared to be empty. Could you tell me which items you'd like me to handle?",
        )

    if anthropic_client is None:
        import anthropic
        anthropic_client = anthropic.AsyncAnthropic()

    import json
    items_json = json.dumps(briefing_items, indent=2, default=str)

    system_prompt = f"""You are parsing a loan officer's reply to their morning briefing email.

The briefing contained these numbered items:
{items_json}

The loan officer replied with natural language instructions about which items to handle.

Extract structured data. Return valid JSON matching this schema:
- handled_items: list of item numbers the LO wants handled
- skipped_items: list of item numbers the LO explicitly wants skipped
- overrides: list of objects with item_number, new_action_type (if changed), instruction_delta (what changed), requires_validation (list of checks needed)
- bulk_action: null or object with type ("handle_all" or "handle_except") and except_items list
- free_text_instructions: list of instructions that don't map to any briefing item
- confidence: float 0-1 of how confident you are in the parse
- requires_clarification: boolean
- clarification_question: string or null

Rules:
- "Handle 1, 3, 5" → handled_items=[1,3,5]
- "Do everything" → bulk_action={{type: "handle_all", except_items: []}}
- "Do everything except 2" → bulk_action={{type: "handle_except", except_items: [2]}}
- "For item 4, call instead of emailing" → overrides with item_number=4, new_action_type="schedule_call"
- Anything that doesn't map to an item goes in free_text_instructions
- If the reply is ambiguous, set requires_clarification=true"""

    response = await anthropic_client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        system=system_prompt,
        messages=[{"role": "user", "content": reply_text}],
    )

    try:
        raw = response.content[0].text
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = re.sub(r'^```\w*\n?', '', raw)
            raw = re.sub(r'\n?```$', '', raw)
        parsed = json.loads(raw)
        return ParsedReply(**parsed)
    except Exception as e:
        logger.error("Failed to parse Claude response: %s", e)
        return ParsedReply(
            handled_items=[],
            skipped_items=[],
            overrides=[],
            confidence=0.0,
            requires_clarification=True,
            clarification_question="I had trouble understanding your reply. Could you try rephrasing which items you'd like me to handle?",
        )
```

- [ ] **Step 4: Run all parser tests**

```bash
cd backend && python -m pytest tests/test_briefing_reply_parser.py -v
```

Expected: PASS for `TestQuotedReplyStripping`, `TestApprovalClassification`, `TestParsedReplySchema`.

- [ ] **Step 5: Commit**

```bash
git add backend/services/briefing_reply_parser.py backend/tests/test_briefing_reply_parser.py
git commit -m "feat: reply parser with quoted-reply stripping, approval classification, Claude extraction"
```

---

### Task 14: Create executor (pre-flight validation + tool dispatch)

**Files:**
- Create: `backend/services/briefing_executor.py`
- Test: `backend/tests/test_briefing_executor.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_briefing_executor.py`:

```python
"""Tests for briefing task executor — pre-flight validation, risk gating, tool dispatch."""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from services.briefing_executor import BriefingExecutor
from database.models.briefing_thread import BriefingTask


class TestPreflightValidation:
    def setup_method(self):
        self.db = MagicMock()
        self.executor = BriefingExecutor(self.db, organization_id=1, user_id=10)

    @pytest.mark.asyncio
    async def test_send_email_blocked_by_tcpa_optout(self):
        task = MagicMock(
            action_type="send_borrower_email",
            action_params={"borrower_id": 1, "to": "test@example.com"},
        )
        borrower = MagicMock(tcpa_opt_out=True)
        self.db.query.return_value.filter.return_value.first.return_value = borrower
        result = await self.executor.run_preflight(task)
        assert result["passed"] is False
        assert "tcpa" in result["reason"].lower()

    @pytest.mark.asyncio
    async def test_send_email_passes_clean(self):
        task = MagicMock(
            action_type="send_borrower_email",
            action_params={"borrower_id": 1, "to": "test@example.com"},
        )
        borrower = MagicMock(tcpa_opt_out=False, email="test@example.com")
        self.db.query.return_value.filter.return_value.first.return_value = borrower
        result = await self.executor.run_preflight(task)
        assert result["passed"] is True


class TestRiskGating:
    def test_high_risk_action_flagged(self):
        executor = BriefingExecutor(MagicMock(), organization_id=1, user_id=10)
        task = MagicMock(action_type="update_pipeline_stage", risk_level="high")
        assert executor.is_high_risk(task) is True

    def test_low_risk_action_not_flagged(self):
        executor = BriefingExecutor(MagicMock(), organization_id=1, user_id=10)
        task = MagicMock(action_type="create_crm_task", risk_level="low")
        assert executor.is_high_risk(task) is False

    def test_low_confidence_flagged(self):
        executor = BriefingExecutor(MagicMock(), organization_id=1, user_id=10)
        task = MagicMock(confidence_score=0.6, risk_level="low")
        assert executor.needs_clarification(task) is True

    def test_high_confidence_not_flagged(self):
        executor = BriefingExecutor(MagicMock(), organization_id=1, user_id=10)
        task = MagicMock(confidence_score=0.95, risk_level="low")
        assert executor.needs_clarification(task) is False


class TestApprovalFiltering:
    def test_bulk_approve_excludes_high_risk(self):
        executor = BriefingExecutor(MagicMock(), organization_id=1, user_id=10)
        tasks = [
            MagicMock(briefing_item_number=1, action_type="send_borrower_email", risk_level="low"),
            MagicMock(briefing_item_number=2, action_type="update_pipeline_stage", risk_level="high"),
            MagicMock(briefing_item_number=3, action_type="create_crm_task", risk_level="low"),
        ]
        approved = executor.filter_by_approval("approve", tasks, task_numbers=[])
        assert len(approved) == 2
        assert all(t.briefing_item_number != 2 for t in approved)

    def test_approve_all_includes_high_risk(self):
        executor = BriefingExecutor(MagicMock(), organization_id=1, user_id=10)
        tasks = [
            MagicMock(briefing_item_number=1, action_type="send_borrower_email", risk_level="low"),
            MagicMock(briefing_item_number=2, action_type="update_pipeline_stage", risk_level="high"),
        ]
        approved = executor.filter_by_approval("approve_all", tasks, task_numbers=[])
        assert len(approved) == 2

    def test_approve_specific(self):
        executor = BriefingExecutor(MagicMock(), organization_id=1, user_id=10)
        tasks = [
            MagicMock(briefing_item_number=1),
            MagicMock(briefing_item_number=2),
            MagicMock(briefing_item_number=3),
        ]
        approved = executor.filter_by_approval("approve_specific", tasks, task_numbers=[1, 3])
        assert len(approved) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && python -m pytest tests/test_briefing_executor.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement the executor**

Create `backend/services/briefing_executor.py`:

```python
"""Briefing task executor — pre-flight validation, risk gating, sequential tool dispatch."""
import logging
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session
from database.models.briefing_thread import BriefingTask
from schemas.briefing_thread import HIGH_RISK_ACTIONS, ACTION_TOOL_MAP
from services.briefing_audit_service import BriefingAuditService

logger = logging.getLogger(__name__)

CONFIDENCE_THRESHOLD = 0.75


class BriefingExecutor:
    def __init__(self, db: Session, organization_id: int, user_id: int):
        self.db = db
        self.organization_id = organization_id
        self.user_id = user_id
        self.audit = BriefingAuditService(db, organization_id)

    def is_high_risk(self, task) -> bool:
        return (
            getattr(task, "action_type", "") in HIGH_RISK_ACTIONS
            or getattr(task, "risk_level", "low") == "high"
        )

    def needs_clarification(self, task) -> bool:
        return getattr(task, "confidence_score", 1.0) < CONFIDENCE_THRESHOLD

    def filter_by_approval(
        self,
        intent: str,
        tasks: list,
        task_numbers: list[int],
    ) -> list:
        if intent == "approve_all":
            return list(tasks)
        elif intent == "approve_specific":
            return [t for t in tasks if t.briefing_item_number in task_numbers]
        elif intent == "approve_except":
            return [t for t in tasks if t.briefing_item_number not in task_numbers]
        else:
            # "approve" — exclude high-risk
            return [t for t in tasks if not self.is_high_risk(t)]

    async def run_preflight(self, task) -> dict:
        """Run pre-flight validation for a single task. Returns {passed, reason, checks}."""
        checks = []
        action_type = task.action_type
        params = task.action_params or {}

        if action_type in ("send_borrower_email", "send_checklist", "schedule_call"):
            borrower_id = params.get("borrower_id")
            if borrower_id:
                from database.models.borrower import BorrowerProfile
                borrower = self.db.query(BorrowerProfile).filter(
                    BorrowerProfile.id == borrower_id,
                ).first()
                if borrower and getattr(borrower, "tcpa_opt_out", False):
                    return {
                        "passed": False,
                        "reason": "TCPA opt-out: borrower has opted out of contact.",
                        "checks": [{"check": "tcpa_opt_out", "passed": False}],
                    }
                checks.append({"check": "tcpa_opt_out", "passed": True})

        if action_type in ("send_borrower_email", "send_realtor_update", "send_checklist"):
            to_email = params.get("to")
            if to_email:
                checks.append({"check": "email_valid", "passed": bool(to_email and "@" in to_email)})

        return {"passed": True, "reason": None, "checks": checks}

    async def execute_task(self, task: BriefingTask, thread_id: int) -> dict:
        """Execute a single approved task via the tool registry."""
        tool_name = ACTION_TOOL_MAP.get(task.action_type)
        if not tool_name:
            return {"success": False, "error": f"Unknown action type: {task.action_type}"}

        task.status = "executing"
        task.executed_at = datetime.now(timezone.utc)
        self.db.flush()

        self.audit.log_event(
            thread_id=thread_id,
            task_id=task.id,
            event_type="tool_call",
            actor="aria",
            payload={"tool": tool_name, "action_type": task.action_type, "params": task.action_params or {}},
        )

        try:
            from agents.tools.base import ToolRegistry
            tool_def = ToolRegistry.get(tool_name)
            if not tool_def:
                raise RuntimeError(f"Tool '{tool_name}' not found in registry")

            result = await tool_def.func(
                **(task.action_params or {}),
                db=self.db,
                user_id=self.user_id,
                organization_id=self.organization_id,
            )

            task.status = "completed"
            task.result_data = result if isinstance(result, dict) else {"result": str(result)}
            self.db.flush()
            return {"success": True, "result": task.result_data}

        except Exception as e:
            logger.exception("Task %s failed: %s", task.id, e)
            task.status = "failed"
            task.error_message = str(e)
            self.db.flush()
            return {"success": False, "error": str(e)}

    async def execute_batch(self, tasks: list[BriefingTask], thread_id: int) -> list[dict]:
        """Execute a batch of approved tasks sequentially.

        A single task failure does not halt the batch, EXCEPT: if update_pipeline_stage
        fails, skip dependent tasks.
        """
        results = []
        stage_failed = False

        for task in tasks:
            if stage_failed and task.action_type != "update_pipeline_stage":
                task.status = "failed"
                task.error_message = "Skipped: pipeline stage transition failed"
                self.db.flush()
                results.append({"success": False, "error": task.error_message, "task_id": task.id})
                continue

            preflight = await self.run_preflight(task)
            if not preflight["passed"]:
                task.status = "failed_preflight"
                task.preflight_result = preflight
                task.error_message = preflight["reason"]
                self.db.flush()
                results.append({"success": False, "error": preflight["reason"], "task_id": task.id})
                continue

            task.preflight_result = preflight
            result = await self.execute_task(task, thread_id)
            results.append({**result, "task_id": task.id})

            if not result["success"] and task.action_type == "update_pipeline_stage":
                stage_failed = True

        return results
```

- [ ] **Step 4: Run tests**

```bash
cd backend && python -m pytest tests/test_briefing_executor.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/briefing_executor.py backend/tests/test_briefing_executor.py
git commit -m "feat: briefing executor with pre-flight validation, risk gating, batch execution"
```

---

### Task 15: Create Aria mailbox service (Graph app-only)

**Files:**
- Create: `backend/services/aria_mailbox_service.py`

- [ ] **Step 1: Create the service**

Create `backend/services/aria_mailbox_service.py`. This uses Microsoft Graph with app-only authentication (client_credentials flow) to send from and poll the `aria@perenniaai.com` shared mailbox.

```python
"""Aria mailbox service — send-from and poll-inbox for aria@perenniaai.com.

Uses Microsoft Graph with app-only (client_credentials) authentication.
Environment variables:
- ARIA_GRAPH_TENANT_ID: Azure AD tenant ID
- ARIA_GRAPH_CLIENT_ID: App registration client ID
- ARIA_GRAPH_CLIENT_SECRET: App registration client secret
- ARIA_MAILBOX_ADDRESS: defaults to aria@perenniaai.com
"""
import os
import logging
import httpx
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
TOKEN_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"

_cached_token: Optional[dict] = None


async def _get_access_token() -> str:
    """Obtain an app-only access token via client_credentials grant."""
    global _cached_token
    if _cached_token and _cached_token["expires_at"] > datetime.now(timezone.utc).timestamp():
        return _cached_token["access_token"]

    tenant = os.getenv("ARIA_GRAPH_TENANT_ID", "")
    client_id = os.getenv("ARIA_GRAPH_CLIENT_ID", "")
    client_secret = os.getenv("ARIA_GRAPH_CLIENT_SECRET", "")

    if not all([tenant, client_id, client_secret]):
        raise RuntimeError("ARIA_GRAPH_TENANT_ID, ARIA_GRAPH_CLIENT_ID, ARIA_GRAPH_CLIENT_SECRET required")

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            TOKEN_URL.format(tenant=tenant),
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
                "scope": "https://graph.microsoft.com/.default",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        _cached_token = {
            "access_token": data["access_token"],
            "expires_at": datetime.now(timezone.utc).timestamp() + data.get("expires_in", 3600) - 60,
        }
        return _cached_token["access_token"]


def _mailbox() -> str:
    return os.getenv("ARIA_MAILBOX_ADDRESS", "aria@perenniaai.com")


async def send_email(
    to: list[str],
    subject: str,
    body_html: str,
    thread_token: Optional[str] = None,
    in_reply_to: Optional[str] = None,
    cc: Optional[list[str]] = None,
) -> dict:
    """Send an email from aria@perenniaai.com via Graph.

    Returns: {"success": bool, "message_id": str|None, "error": str|None}
    """
    token = await _get_access_token()
    mailbox = _mailbox()

    headers_list = []
    if thread_token:
        headers_list.append({"name": "X-Perennia-Thread-Id", "value": f"briefing_{thread_token}"})

    message = {
        "subject": subject,
        "body": {"contentType": "HTML", "content": body_html},
        "toRecipients": [{"emailAddress": {"address": addr}} for addr in to],
        "internetMessageHeaders": headers_list,
    }
    if cc:
        message["ccRecipients"] = [{"emailAddress": {"address": addr}} for addr in cc]

    payload = {"message": message, "saveToSentItems": True}

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{GRAPH_BASE}/users/{mailbox}/sendMail",
            json=payload,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )

    if resp.status_code == 202:
        return {"success": True, "message_id": None, "error": None}
    else:
        error = resp.text[:500]
        logger.error("Graph sendMail failed: %s %s", resp.status_code, error)
        return {"success": False, "message_id": None, "error": error}


async def poll_inbox(since_minutes: int = 2) -> list[dict]:
    """Poll unread messages in the aria@ inbox.

    Returns list of dicts: {id, sender, subject, body, received_at, in_reply_to, references, headers}
    """
    token = await _get_access_token()
    mailbox = _mailbox()

    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=since_minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")

    params = {
        "$filter": f"isRead eq false and receivedDateTime ge {cutoff}",
        "$select": "id,from,subject,body,receivedDateTime,internetMessageHeaders",
        "$top": "50",
        "$orderby": "receivedDateTime asc",
    }

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GRAPH_BASE}/users/{mailbox}/messages",
            params=params,
            headers={"Authorization": f"Bearer {token}"},
        )

    if resp.status_code != 200:
        logger.error("Graph poll failed: %s %s", resp.status_code, resp.text[:500])
        return []

    messages = []
    for msg in resp.json().get("value", []):
        hdrs = {h["name"]: h["value"] for h in msg.get("internetMessageHeaders", [])}
        messages.append({
            "id": msg["id"],
            "sender": msg.get("from", {}).get("emailAddress", {}).get("address", ""),
            "subject": msg.get("subject", ""),
            "body": msg.get("body", {}).get("content", ""),
            "received_at": msg.get("receivedDateTime"),
            "in_reply_to": hdrs.get("In-Reply-To"),
            "references": hdrs.get("References"),
            "thread_token_header": hdrs.get("X-Perennia-Thread-Id"),
        })

    return messages


async def mark_as_read(message_id: str) -> None:
    """Mark a message as read so it's not re-polled."""
    token = await _get_access_token()
    mailbox = _mailbox()
    async with httpx.AsyncClient() as client:
        await client.patch(
            f"{GRAPH_BASE}/users/{mailbox}/messages/{message_id}",
            json={"isRead": True},
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
```

- [ ] **Step 2: Verify syntax**

```bash
cd backend && python -c "import py_compile; py_compile.compile('services/aria_mailbox_service.py', doraise=True); print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add backend/services/aria_mailbox_service.py
git commit -m "feat: Aria mailbox service — Graph app-only auth, send-from and poll-inbox"
```

---

## Phase 4: Email Templates

### Task 16: Create confirmation + results email templates

**Files:**
- Create: `backend/services/briefing_email_renderer.py`

- [ ] **Step 1: Create the email renderer**

Create `backend/services/briefing_email_renderer.py`:

```python
"""Email templates for the interactive briefing conversation loop.

Renders confirmation and results emails with the org's white-label branding.
All user-controlled values are HTML-escaped.
"""
import html
from typing import Optional


def _esc(value) -> str:
    return html.escape(str(value)) if value is not None else ""


def render_confirmation_email(
    lo_name: str,
    tasks: list[dict],
    free_text: list[str],
    thread_token: str,
    primary_color: str = "#218d8d",
    company_name: str = "Perennia AI",
) -> str:
    """Render the confirmation email (Step 3 of the conversation loop).

    Each task dict must contain: number, summary, action_description, confidence, risk_level.
    """
    task_rows = []
    for t in tasks:
        risk_badge = ""
        if t.get("risk_level") == "high":
            risk_badge = ' <span style="color:#EF4444;font-weight:bold;">[HIGH RISK]</span>'

        conf = t.get("confidence", 0)
        conf_pct = f"{conf * 100:.0f}%"

        task_rows.append(f"""
        <tr>
          <td style="padding:12px;border-bottom:1px solid #E5E7EB;">
            <strong>{t['number']}.</strong> {_esc(t['summary'])}{risk_badge}<br>
            <span style="color:#6B7280;font-size:13px;">→ {_esc(t['action_description'])}</span><br>
            <span style="color:#9CA3AF;font-size:12px;">confidence {conf_pct}, risk {_esc(t.get('risk_level', 'low'))}</span>
          </td>
        </tr>""")

    free_text_section = ""
    if free_text:
        items = "".join(f"<li>{_esc(ft)}</li>" for ft in free_text)
        free_text_section = f"""
        <div style="margin-top:20px;padding:12px;background:#FEF3C7;border-radius:8px;">
          <strong style="color:#92400E;">I noticed but won't act on:</strong>
          <ul style="margin:8px 0 0 0;padding-left:20px;">{items}</ul>
        </div>"""

    token_comment = f"<!-- perennia-thread:{thread_token} -->"

    return f"""{token_comment}
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;max-width:600px;margin:0 auto;padding:20px;color:#1F2937;">
  <div style="background:linear-gradient(135deg,{primary_color},{primary_color}dd);padding:20px;border-radius:12px 12px 0 0;">
    <h2 style="color:white;margin:0;">Here's what I'll do</h2>
    <p style="color:rgba(255,255,255,0.8);margin:4px 0 0 0;">{_esc(company_name)}</p>
  </div>
  <div style="border:1px solid #E5E7EB;border-top:none;padding:20px;border-radius:0 0 12px 12px;">
    <table style="width:100%;border-collapse:collapse;">
      {"".join(task_rows)}
    </table>
    {free_text_section}
    <div style="margin-top:24px;padding:16px;background:#F0FDF4;border-radius:8px;text-align:center;">
      <p style="margin:0;font-size:15px;">
        Reply <strong>"approved"</strong> to proceed, or tell me what to change.
      </p>
    </div>
  </div>
</body>
</html>"""


def render_results_email(
    lo_name: str,
    completed: list[dict],
    failed: list[dict],
    needs_attention: list[dict],
    carryover: list[dict],
    compliance_flags: list[dict],
    sla_changes: list[dict],
    thread_token: str,
    primary_color: str = "#218d8d",
    company_name: str = "Perennia AI",
) -> str:
    """Render the results email (Step 5 of the conversation loop)."""

    def _result_row(items, icon, status_color):
        if not items:
            return ""
        rows = []
        for item in items:
            rows.append(f"""
            <tr>
              <td style="padding:10px;border-bottom:1px solid #E5E7EB;">
                {icon} <strong>{_esc(item.get('summary', ''))}</strong><br>
                <span style="color:{status_color};font-size:13px;">→ {_esc(item.get('detail', ''))}</span>
              </td>
            </tr>""")
        return "".join(rows)

    completed_rows = _result_row(completed, "✅", "#059669")
    failed_rows = _result_row(failed, "❌", "#DC2626")
    attention_rows = _result_row(needs_attention, "⚠️", "#D97706")

    carryover_section = ""
    if carryover:
        items = "".join(f"<li>{_esc(c.get('summary', ''))}</li>" for c in carryover)
        carryover_section = f"""
        <div style="margin-top:16px;">
          <h3 style="color:#6B7280;margin:0 0 8px;">📋 Carryover to tomorrow</h3>
          <ul style="margin:0;padding-left:20px;">{items}</ul>
        </div>"""

    flags_content = "No flags raised during execution."
    if compliance_flags:
        flags_content = "".join(f"<li>⚖️ {_esc(f.get('detail', ''))}</li>" for f in compliance_flags)
        flags_content = f"<ul style='margin:0;padding-left:20px;'>{flags_content}</ul>"

    sla_content = "No SLA risk changes during execution."
    if sla_changes:
        sla_content = "".join(f"<li>📊 {_esc(s.get('detail', ''))}</li>" for s in sla_changes)
        sla_content = f"<ul style='margin:0;padding-left:20px;'>{sla_content}</ul>"

    total = len(completed) + len(failed) + len(needs_attention)
    summary_line = f"{len(completed)} of {total} tasks completed"

    token_comment = f"<!-- perennia-thread:{thread_token} -->"

    return f"""{token_comment}
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;max-width:600px;margin:0 auto;padding:20px;color:#1F2937;">
  <div style="background:linear-gradient(135deg,{primary_color},{primary_color}dd);padding:20px;border-radius:12px 12px 0 0;">
    <h2 style="color:white;margin:0;">✅ {_esc(summary_line)}</h2>
    <p style="color:rgba(255,255,255,0.8);margin:4px 0 0 0;">{_esc(company_name)}</p>
  </div>
  <div style="border:1px solid #E5E7EB;border-top:none;padding:20px;border-radius:0 0 12px 12px;">
    <table style="width:100%;border-collapse:collapse;">
      {completed_rows}
      {failed_rows}
      {attention_rows}
    </table>
    {carryover_section}
    <div style="margin-top:20px;padding:12px;background:#F9FAFB;border-radius:8px;">
      <h3 style="margin:0 0 8px;color:#374151;">Compliance Flags</h3>
      {flags_content}
    </div>
    <div style="margin-top:12px;padding:12px;background:#F9FAFB;border-radius:8px;">
      <h3 style="margin:0 0 8px;color:#374151;">SLA Risk Changes</h3>
      {sla_content}
    </div>
    <div style="margin-top:20px;text-align:center;color:#9CA3AF;font-size:13px;">
      No further action needed unless noted above.
    </div>
  </div>
</body>
</html>"""
```

- [ ] **Step 2: Verify syntax**

```bash
cd backend && python -c "import py_compile; py_compile.compile('services/briefing_email_renderer.py', doraise=True); print('OK')"
```

- [ ] **Step 3: Quick smoke test**

```bash
cd backend && python -c "
from services.briefing_email_renderer import render_confirmation_email, render_results_email
html = render_confirmation_email('Tim', [{'number': 1, 'summary': 'Follow up Torres', 'action_description': 'Send follow-up email', 'confidence': 0.96, 'risk_level': 'low'}], [], 'test-token-123')
assert 'Follow up Torres' in html
assert 'perennia-thread:test-token-123' in html
print('Confirmation: OK')

html = render_results_email('Tim', [{'summary': 'Email sent to Torres', 'detail': 'Delivered at 8:47 AM'}], [], [], [], [], [], 'test-token-123')
assert 'Email sent to Torres' in html
assert 'No flags raised' in html
print('Results: OK')
"
```

- [ ] **Step 4: Commit**

```bash
git add backend/services/briefing_email_renderer.py
git commit -m "feat: confirmation and results email renderers with HTML escaping and branding"
```

---

### Task 17: Update briefing email template with thread token

**Files:**
- Modify: `backend/templates/morning_briefing_email.py`

- [ ] **Step 1: Add thread_token parameter to render function**

Read `backend/templates/morning_briefing_email.py`. Add `thread_token: Optional[str] = None` parameter to `render_briefing_email()`. When provided, inject the hidden HTML comment and custom header reference into the rendered email:

```python
def render_briefing_email(
    user_name, briefing_date, level, ai_narrative,
    pipeline, at_risk, stale_leads, appointments, conditions, yesterday, team,
    app_url="https://app.perenniaai.com",
    company_name="The Tim Loss Team",
    logo_url=None,
    primary_color="#218d8d",
    secondary_color=None,
    thread_token=None,  # NEW
) -> str:
```

At the very top of the returned HTML string, prepend:

```python
token_comment = f"<!-- perennia-thread:{thread_token} -->" if thread_token else ""
```

And include `{token_comment}` before the `<!DOCTYPE html>`.

Also add numbered item references to each briefing section (e.g., `#1`, `#2`) and a reply prompt at the bottom of the email:

```python
reply_prompt = ""
if thread_token:
    reply_prompt = '''
    <div style="margin-top:24px;padding:16px;background:#F0FDF4;border-radius:8px;text-align:center;">
      <p style="margin:0;font-size:15px;">
        Reply to this email with what you'd like me to handle.<br>
        <span style="color:#6B7280;font-size:13px;">e.g., "Handle 1, 3, and 5" or "Do everything except 2"</span>
      </p>
    </div>'''
```

- [ ] **Step 2: Verify syntax and existing tests still pass**

```bash
cd backend && python -c "import py_compile; py_compile.compile('templates/morning_briefing_email.py', doraise=True); print('OK')"
cd backend && python -m pytest tests/test_email_templates.py -v
```

- [ ] **Step 3: Commit**

```bash
git add backend/templates/morning_briefing_email.py
git commit -m "feat: add thread_token and reply prompt to briefing email template"
```

---

## Phase 5: Celery Tasks

### Task 18: Create briefing thread Celery tasks

**Files:**
- Create: `backend/tasks/briefing_thread_tasks.py`
- Test: `backend/tests/test_briefing_thread_tasks.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_briefing_thread_tasks.py`:

```python
"""Tests for briefing thread Celery tasks."""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, timezone


class TestReplyMatching:
    def test_match_by_in_reply_to(self):
        from tasks.briefing_thread_tasks import match_reply_to_thread
        db = MagicMock()
        thread = MagicMock(id=1, outbound_message_id="<msg123@graph>")
        db.query.return_value.filter.return_value.first.return_value = thread
        result = match_reply_to_thread(db, {
            "in_reply_to": "<msg123@graph>",
            "thread_token_header": None,
            "sender": "lo@example.com",
        })
        assert result == thread

    def test_match_by_thread_token_header(self):
        from tasks.briefing_thread_tasks import match_reply_to_thread
        db = MagicMock()
        db.query.return_value.filter.return_value.first.side_effect = [None, MagicMock(id=2)]
        result = match_reply_to_thread(db, {
            "in_reply_to": None,
            "thread_token_header": "briefing_abc-def-123",
            "sender": "lo@example.com",
        })
        assert result is not None

    def test_no_match_returns_none(self):
        from tasks.briefing_thread_tasks import match_reply_to_thread
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        result = match_reply_to_thread(db, {
            "in_reply_to": None,
            "thread_token_header": None,
            "sender": "unknown@example.com",
        })
        assert result is None


class TestSenderAuthorization:
    def test_authorized_sender(self):
        from tasks.briefing_thread_tasks import is_authorized_sender
        thread = MagicMock()
        thread.user = MagicMock(email="lo@example.com")
        assert is_authorized_sender(thread, "lo@example.com") is True

    def test_unauthorized_sender(self):
        from tasks.briefing_thread_tasks import is_authorized_sender
        thread = MagicMock()
        thread.user = MagicMock(email="lo@example.com")
        assert is_authorized_sender(thread, "manager@example.com") is False
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && python -m pytest tests/test_briefing_thread_tasks.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement the Celery tasks**

Create `backend/tasks/briefing_thread_tasks.py`:

```python
"""Celery tasks for the interactive briefing thread system.

Tasks:
- poll_briefing_replies: Every 60s, poll aria@ inbox and dispatch replies
- process_briefing_reply: Parse reply, extract tasks, send confirmation
- execute_briefing_tasks: Run approved tasks, send results
- expire_stale_threads: Every 30min, expire threads past 4h
"""
import logging
import asyncio
from datetime import datetime, timezone
from typing import Optional
from contextlib import contextmanager

from sqlalchemy import text
from sqlalchemy.orm import Session, joinedload

from tasks.celery_app import celery_app
from db import SessionLocal
from database.models.briefing_thread import BriefingThread, BriefingTask
from schemas.briefing_thread import TERMINAL_STATES, ApprovalIntent

logger = logging.getLogger(__name__)


@contextmanager
def _get_session(org_id: Optional[int] = None):
    db = SessionLocal()
    try:
        if org_id:
            db.execute(text("SET app.current_tenant = :org_id"), {"org_id": str(org_id)})
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def match_reply_to_thread(db: Session, message: dict) -> Optional[BriefingThread]:
    """Match an inbound reply to an active thread. Three-strategy priority."""
    in_reply_to = message.get("in_reply_to")
    if in_reply_to:
        thread = db.query(BriefingThread).filter(
            BriefingThread.outbound_message_id == in_reply_to,
            BriefingThread.state.notin_(list(TERMINAL_STATES)),
        ).first()
        if thread:
            return thread

    token_header = message.get("thread_token_header")
    if token_header:
        token = token_header.replace("briefing_", "")
        thread = db.query(BriefingThread).filter(
            BriefingThread.thread_token == token,
            BriefingThread.state.notin_(list(TERMINAL_STATES)),
        ).first()
        if thread:
            return thread

    sender = message.get("sender", "").lower()
    if sender:
        from database.models.user import User
        user = db.query(User).filter(User.email == sender).first()
        if user:
            thread = db.query(BriefingThread).filter(
                BriefingThread.user_id == user.id,
                BriefingThread.state.in_(["AWAITING_REPLY", "AWAITING_APPROVAL"]),
            ).order_by(BriefingThread.created_at.desc()).first()
            if thread:
                return thread

    return None


def is_authorized_sender(thread: BriefingThread, sender_email: str) -> bool:
    """Only the LO who received the briefing can drive its thread."""
    user = thread.user
    if not user:
        return False
    return user.email.lower() == sender_email.lower()


@celery_app.task(name="tasks.briefing_thread_tasks.poll_briefing_replies", queue="default")
def poll_briefing_replies():
    """Poll the aria@ inbox for replies to active briefing threads."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_poll_briefing_replies_async())
    finally:
        loop.close()


async def _poll_briefing_replies_async():
    from services.aria_mailbox_service import poll_inbox, mark_as_read
    from services.briefing_audit_service import BriefingAuditService

    messages = await poll_inbox(since_minutes=2)
    dispatched = 0

    for msg in messages:
        with _get_session() as db:
            thread = match_reply_to_thread(db, msg)
            if not thread:
                logger.info("No matching thread for message from %s", msg["sender"])
                await mark_as_read(msg["id"])
                continue

            if not is_authorized_sender(thread, msg["sender"]):
                audit = BriefingAuditService(db, thread.organization_id)
                audit.log_event(
                    thread_id=thread.id,
                    event_type="email_received",
                    actor=f"unauthorized:{msg['sender']}",
                    payload={"subject": msg["subject"], "sender": msg["sender"]},
                )
                await mark_as_read(msg["id"])
                continue

            if thread.state in ("AWAITING_REPLY", "CLARIFICATION_SENT"):
                process_briefing_reply.delay(thread.id, msg["body"], msg["id"])
            elif thread.state == "AWAITING_APPROVAL":
                _handle_approval.delay(thread.id, msg["body"], msg["id"])

            await mark_as_read(msg["id"])
            dispatched += 1

    return {"polled": len(messages), "dispatched": dispatched}


@celery_app.task(name="tasks.briefing_thread_tasks.process_briefing_reply", queue="ai_tasks")
def process_briefing_reply(thread_id: int, reply_body: str, message_id: str):
    """Parse the LO's reply, extract tasks, send confirmation email."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_process_reply_async(thread_id, reply_body, message_id))
    finally:
        loop.close()


async def _process_reply_async(thread_id: int, reply_body: str, message_id: str):
    from services.briefing_reply_parser import strip_quoted_reply, parse_lo_reply
    from services.briefing_thread_service import BriefingThreadService
    from services.briefing_executor import BriefingExecutor
    from services.briefing_email_renderer import render_confirmation_email
    from services import aria_mailbox_service

    with _get_session() as db:
        thread = db.query(BriefingThread).options(
            joinedload(BriefingThread.tasks)
        ).filter(BriefingThread.id == thread_id).first()
        if not thread:
            return {"error": "Thread not found"}

        service = BriefingThreadService(db, thread.organization_id)

        body = service.record_inbound_message(thread, message_id, reply_body)
        if body is None:
            return {"status": "duplicate"}

        service.transition(thread, "PARSING_INSTRUCTIONS")

        stripped = strip_quoted_reply(reply_body)
        if not stripped:
            service.transition(thread, "CLARIFICATION_SENT")
            return {"status": "empty_reply"}

        parsed = await parse_lo_reply(stripped, thread.briefing_items or [])
        thread.extracted_tasks = parsed.model_dump()

        if parsed.requires_clarification:
            service.transition(thread, "CLARIFICATION_SENT")
            # TODO: send clarification email
            return {"status": "clarification_needed"}

        # Resolve bulk actions
        all_items = list(range(1, len(thread.briefing_items or []) + 1))
        handled = set(parsed.handled_items)
        if parsed.bulk_action:
            if parsed.bulk_action.type == "handle_all":
                handled = set(all_items) - set(parsed.bulk_action.except_items)
            elif parsed.bulk_action.type == "handle_except":
                handled = set(all_items) - set(parsed.bulk_action.except_items)

        # Create BriefingTask records
        from schemas.briefing_thread import ACTION_TOOL_MAP, SUPPORTED_ACTION_TYPES
        executor = BriefingExecutor(db, thread.organization_id, thread.user_id)
        tasks_for_confirmation = []

        for item_num in sorted(handled):
            if item_num < 1 or item_num > len(thread.briefing_items):
                continue
            item = thread.briefing_items[item_num - 1]
            action_type = item.get("next_best_action", "create_crm_task")

            override = next((o for o in parsed.overrides if o.item_number == item_num), None)
            if override and override.new_action_type:
                action_type = override.new_action_type

            if action_type not in SUPPORTED_ACTION_TYPES:
                action_type = "create_crm_task"

            task = BriefingTask(
                thread_id=thread.id,
                organization_id=thread.organization_id,
                briefing_item_number=item_num,
                briefing_item_summary=item.get("summary", ""),
                action_type=action_type,
                action_params=item.get("action_params", {}),
                tool_name=ACTION_TOOL_MAP.get(action_type),
                lo_override_notes=override.instruction_delta if override else None,
                confidence_score=parsed.confidence,
                risk_level="high" if executor.is_high_risk(
                    type("_", (), {"action_type": action_type, "risk_level": "low"})
                ) else "low",
                status="pending",
                idempotency_key=f"bt_{thread.id}_{item_num}_attempt_1",
            )
            db.add(task)
            tasks_for_confirmation.append({
                "number": item_num,
                "summary": item.get("summary", ""),
                "action_description": f"Using {action_type}",
                "confidence": parsed.confidence,
                "risk_level": task.risk_level,
            })

        db.flush()

        confirmation_html = render_confirmation_email(
            lo_name="",
            tasks=tasks_for_confirmation,
            free_text=parsed.free_text_instructions,
            thread_token=str(thread.thread_token),
        )

        service.transition(thread, "CONFIRMATION_SENT")
        service.transition(thread, "AWAITING_APPROVAL")

        user = db.query(db.query(BriefingThread).filter(BriefingThread.id == thread_id).first().__class__).first()
        # Send confirmation email
        from database.models.user import User
        lo = db.query(User).filter(User.id == thread.user_id).first()
        if lo:
            await aria_mailbox_service.send_email(
                to=[lo.email],
                subject="Aria — Confirming your tasks",
                body_html=confirmation_html,
                thread_token=str(thread.thread_token),
            )

        return {"status": "confirmation_sent", "task_count": len(tasks_for_confirmation)}


@celery_app.task(name="tasks.briefing_thread_tasks.handle_approval", queue="ai_tasks")
def _handle_approval(thread_id: int, reply_body: str, message_id: str):
    """Process an approval reply on a thread in AWAITING_APPROVAL state."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_handle_approval_async(thread_id, reply_body, message_id))
    finally:
        loop.close()


async def _handle_approval_async(thread_id: int, reply_body: str, message_id: str):
    from services.briefing_reply_parser import strip_quoted_reply, classify_approval
    from services.briefing_thread_service import BriefingThreadService
    from services.briefing_executor import BriefingExecutor

    with _get_session() as db:
        thread = db.query(BriefingThread).options(
            joinedload(BriefingThread.tasks)
        ).filter(BriefingThread.id == thread_id).first()
        if not thread:
            return {"error": "Thread not found"}

        service = BriefingThreadService(db, thread.organization_id)
        body = service.record_inbound_message(thread, message_id, reply_body)
        if body is None:
            return {"status": "duplicate"}

        stripped = strip_quoted_reply(reply_body)
        approval = classify_approval(stripped)

        if approval.intent == ApprovalIntent.CANCEL:
            service.transition(thread, "CANCELLED")
            return {"status": "cancelled"}

        if approval.intent == ApprovalIntent.MODIFY:
            service.transition(thread, "CONFIRMATION_SENT")
            # Re-parse and re-confirm (loops back)
            process_briefing_reply.delay(thread.id, reply_body, message_id + "_mod")
            return {"status": "modification_loop"}

        # It's an approval — dispatch execution
        executor = BriefingExecutor(db, thread.organization_id, thread.user_id)
        pending_tasks = [t for t in thread.tasks if t.status == "pending"]
        approved = executor.filter_by_approval(
            approval.intent.value, pending_tasks, approval.task_numbers,
        )

        for t in approved:
            t.status = "approved"
        db.flush()

        execute_briefing_tasks.delay(thread.id)
        return {"status": "executing", "approved_count": len(approved)}


@celery_app.task(name="tasks.briefing_thread_tasks.execute_briefing_tasks", queue="ai_tasks")
def execute_briefing_tasks(thread_id: int):
    """Execute all approved tasks and send results email."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_execute_tasks_async(thread_id))
    finally:
        loop.close()


async def _execute_tasks_async(thread_id: int):
    from services.briefing_thread_service import BriefingThreadService
    from services.briefing_executor import BriefingExecutor
    from services.briefing_email_renderer import render_results_email
    from services import aria_mailbox_service

    with _get_session() as db:
        thread = db.query(BriefingThread).options(
            joinedload(BriefingThread.tasks)
        ).filter(BriefingThread.id == thread_id).first()
        if not thread:
            return {"error": "Thread not found"}

        service = BriefingThreadService(db, thread.organization_id)
        service.transition(thread, "EXECUTING")

        executor = BriefingExecutor(db, thread.organization_id, thread.user_id)
        approved_tasks = [t for t in thread.tasks if t.status == "approved"]
        results = await executor.execute_batch(approved_tasks, thread.id)

        # Build results email content
        completed = []
        failed = []
        needs_attention = []
        carryover = []

        for task in thread.tasks:
            if task.status == "completed":
                completed.append({
                    "summary": task.briefing_item_summary,
                    "detail": str(task.result_data) if task.result_data else "Done",
                })
            elif task.status == "failed":
                failed.append({
                    "summary": task.briefing_item_summary,
                    "detail": task.error_message or "Unknown error",
                })
            elif task.status == "failed_preflight":
                needs_attention.append({
                    "summary": task.briefing_item_summary,
                    "detail": task.error_message or "Pre-flight check failed",
                })
            elif task.status == "carryover":
                carryover.append({"summary": task.briefing_item_summary})

        # Gather compliance flags from audit log
        from services.briefing_audit_service import BriefingAuditService
        audit = BriefingAuditService(db, thread.organization_id)
        from database.models.briefing_thread import BriefingAuditLog
        flag_entries = db.query(BriefingAuditLog).filter(
            BriefingAuditLog.thread_id == thread.id,
            BriefingAuditLog.event_type == "compliance_flag",
        ).all()
        compliance_flags = [{"detail": e.payload.get("detail", "")} for e in flag_entries]

        results_html = render_results_email(
            lo_name="",
            completed=completed,
            failed=failed,
            needs_attention=needs_attention,
            carryover=carryover,
            compliance_flags=compliance_flags,
            sla_changes=[],
            thread_token=str(thread.thread_token),
        )

        service.transition(thread, "RESULTS_SENT")

        from database.models.user import User
        lo = db.query(User).filter(User.id == thread.user_id).first()
        if lo:
            await aria_mailbox_service.send_email(
                to=[lo.email],
                subject="Aria — Task results",
                body_html=results_html,
                thread_token=str(thread.thread_token),
            )

        return {"status": "results_sent", "completed": len(completed), "failed": len(failed)}


@celery_app.task(name="tasks.briefing_thread_tasks.expire_stale_threads", queue="default")
def expire_stale_threads():
    """Move threads past 4h expiry to EXPIRED state."""
    from database.models.user import User
    now = datetime.now(timezone.utc)
    expired_count = 0

    with _get_session() as db:
        threads = db.query(BriefingThread).filter(
            BriefingThread.expires_at <= now,
            BriefingThread.state.in_(["AWAITING_REPLY", "AWAITING_APPROVAL"]),
        ).all()

        for thread in threads:
            from services.briefing_audit_service import BriefingAuditService
            audit = BriefingAuditService(db, thread.organization_id)
            audit.log_event(
                thread_id=thread.id,
                event_type="state_transition",
                actor="system",
                payload={"from": thread.state, "to": "EXPIRED", "reason": "4h_expiry"},
            )
            thread.state = "EXPIRED"
            thread.updated_at = now
            expired_count += 1

    return {"expired": expired_count}
```

- [ ] **Step 4: Run tests**

```bash
cd backend && python -m pytest tests/test_briefing_thread_tasks.py -v
```

Expected: PASS

- [ ] **Step 5: Verify syntax**

```bash
cd backend && python -c "import py_compile; py_compile.compile('tasks/briefing_thread_tasks.py', doraise=True); print('OK')"
```

- [ ] **Step 6: Commit**

```bash
git add backend/tasks/briefing_thread_tasks.py backend/tests/test_briefing_thread_tasks.py
git commit -m "feat: Celery tasks for briefing thread system — poll, process, execute, expire"
```

---

## Phase 6: API + Wiring

### Task 19: Create API routes for thread management

**Files:**
- Create: `backend/routes/briefing_thread_routes.py`

- [ ] **Step 1: Create the routes**

Create `backend/routes/briefing_thread_routes.py`:

```python
"""API routes for interactive briefing thread management.

Endpoints:
- GET /api/v1/briefing/threads — list threads for current user
- GET /api/v1/briefing/threads/{thread_id} — thread detail with tasks
- POST /api/v1/briefing/threads/{thread_id}/retry — retry failed tasks
"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from auth.dependencies import get_current_user
from database import get_db
from database.models.briefing_thread import BriefingThread, BriefingTask
from schemas.briefing_thread import BriefingThreadResponse, BriefingTaskResponse, TERMINAL_STATES

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/briefing/threads", tags=["briefing-threads"])


@router.get("")
def list_threads(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    threads = (
        db.query(BriefingThread)
        .filter(
            BriefingThread.organization_id == current_user.organization_id,
            BriefingThread.user_id == current_user.id,
        )
        .order_by(BriefingThread.created_at.desc())
        .limit(20)
        .all()
    )
    return [BriefingThreadResponse.model_validate(t) for t in threads]


@router.get("/{thread_id}")
def get_thread(
    thread_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    thread = (
        db.query(BriefingThread)
        .options(joinedload(BriefingThread.tasks))
        .filter(
            BriefingThread.id == thread_id,
            BriefingThread.organization_id == current_user.organization_id,
            BriefingThread.user_id == current_user.id,
        )
        .first()
    )
    if not thread:
        raise HTTPException(404, "Thread not found")
    return BriefingThreadResponse.model_validate(thread)


@router.get("/active")
def get_active_thread(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    thread = (
        db.query(BriefingThread)
        .options(joinedload(BriefingThread.tasks))
        .filter(
            BriefingThread.organization_id == current_user.organization_id,
            BriefingThread.user_id == current_user.id,
            BriefingThread.state.notin_(list(TERMINAL_STATES)),
        )
        .order_by(BriefingThread.created_at.desc())
        .first()
    )
    if not thread:
        return None
    return BriefingThreadResponse.model_validate(thread)
```

- [ ] **Step 2: Register the router in main.py**

Add to the route registration section in `backend/main.py`:

```python
from routes.briefing_thread_routes import router as briefing_thread_router
app.include_router(briefing_thread_router)
```

- [ ] **Step 3: Verify syntax**

```bash
cd backend && python -c "import py_compile; py_compile.compile('routes/briefing_thread_routes.py', doraise=True); print('OK')"
```

- [ ] **Step 4: Commit**

```bash
git add backend/routes/briefing_thread_routes.py backend/main.py
git commit -m "feat: API routes for briefing thread management"
```

---

### Task 20: Wire into Celery Beat schedule and dispatch_briefings

**Files:**
- Modify: `backend/tasks/celery_app.py`
- Modify: `backend/tasks/morning_briefing_tasks.py`

- [ ] **Step 1: Add new Beat schedule entries**

In `backend/tasks/celery_app.py`, add to the `beat_schedule` dict:

```python
"briefing-poll-replies": {
    "task": "tasks.briefing_thread_tasks.poll_briefing_replies",
    "schedule": 60.0,  # Every 60 seconds
    "options": {"queue": "default"},
},
"briefing-expire-stale": {
    "task": "tasks.briefing_thread_tasks.expire_stale_threads",
    "schedule": crontab(minute="*/30"),  # Every 30 minutes
    "options": {"queue": "default"},
},
```

Also add the task module to the `include` list:

```python
include=[
    # ... existing ...
    "tasks.briefing_thread_tasks",
],
```

- [ ] **Step 2: Wire thread creation into dispatch_briefings**

In `backend/tasks/morning_briefing_tasks.py`, in the `generate_user_briefing` task, after the briefing is delivered successfully (status set to "delivered"), create a `BriefingThread`:

```python
# After briefing is delivered and email sent:
from services.briefing_thread_service import BriefingThreadService

# Check if interactive briefing is enabled for this org
interactive_enabled = getattr(org, 'interactive_briefing_enabled', False) if org else False
if interactive_enabled:
    thread_service = BriefingThreadService(db, org_id)
    briefing_items = _build_briefing_items(context)  # Extract numbered items
    thread = thread_service.create_thread(
        user_id=user_id,
        morning_briefing_id=briefing.id,
        briefing_items=briefing_items,
    )
    # The thread_token is embedded in the email via the render_briefing_email call
```

This wiring is conditional on the feature flag (Task 21).

- [ ] **Step 3: Verify syntax**

```bash
cd backend && python -c "import py_compile; py_compile.compile('tasks/celery_app.py', doraise=True); print('OK')"
cd backend && python -c "import py_compile; py_compile.compile('tasks/morning_briefing_tasks.py', doraise=True); print('OK')"
```

- [ ] **Step 4: Commit**

```bash
git add backend/tasks/celery_app.py backend/tasks/morning_briefing_tasks.py
git commit -m "feat: wire briefing thread tasks into Celery Beat schedule and dispatch"
```

---

## Phase 7: Feature Flags

### Task 21: Add feature flag and kill switch

**Files:**
- Modify: `backend/feature_tiers.py`
- Modify: `backend/tasks/morning_briefing_tasks.py` (guard the thread creation)
- Modify: `backend/tasks/briefing_thread_tasks.py` (guard the executor)

- [ ] **Step 1: Add to feature tiers**

In `backend/feature_tiers.py`, add `"interactive_briefing"` to the CORE tier module list.

- [ ] **Step 2: Add org-level feature flag check**

The feature is gated by two flags on the Organization model:
- `interactive_briefing_enabled` (boolean, default False) — controls whether threads are created
- `interactive_briefing_executor_disabled` (boolean, default False) — emergency kill switch for execution

For V1, these can be checked via a helper:

```python
# In services/briefing_thread_service.py, add:
def is_interactive_briefing_enabled(db: Session, org_id: int) -> bool:
    """Check if interactive briefing is enabled for this org."""
    from database.models.organization import Organization
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        return False
    return getattr(org, 'interactive_briefing_enabled', False)

def is_executor_disabled(db: Session, org_id: int) -> bool:
    """Check the kill switch — stops all task execution."""
    from database.models.organization import Organization
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        return True
    return getattr(org, 'interactive_briefing_executor_disabled', False)
```

- [ ] **Step 3: Guard thread creation in morning_briefing_tasks.py**

In `generate_user_briefing`, wrap the thread creation:

```python
from services.briefing_thread_service import is_interactive_briefing_enabled
if is_interactive_briefing_enabled(db, org_id):
    # ... create thread ...
```

- [ ] **Step 4: Guard executor in briefing_thread_tasks.py**

In `_execute_tasks_async`, add at the top:

```python
from services.briefing_thread_service import is_executor_disabled
if is_executor_disabled(db, thread.organization_id):
    logger.warning("Executor kill switch active for org %s", thread.organization_id)
    return {"status": "executor_disabled"}
```

- [ ] **Step 5: Verify syntax**

```bash
cd backend && python -c "import py_compile; py_compile.compile('feature_tiers.py', doraise=True); print('OK')"
cd backend && python -c "import py_compile; py_compile.compile('services/briefing_thread_service.py', doraise=True); print('OK')"
```

- [ ] **Step 6: Commit**

```bash
git add backend/feature_tiers.py backend/services/briefing_thread_service.py backend/tasks/morning_briefing_tasks.py backend/tasks/briefing_thread_tasks.py
git commit -m "feat: interactive briefing feature flag + executor kill switch"
```

---

## Self-Review Fixes

The following gaps were found during spec cross-reference and must be addressed during implementation:

### Fix A: Rate limits on inbound parsing (§10.3)

In `tasks/briefing_thread_tasks.py`, add rate limit checks at the top of `_process_reply_async`:

```python
from datetime import timedelta

# Max 10 parses per thread per hour
one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
parse_count = db.query(BriefingAuditLog).filter(
    BriefingAuditLog.thread_id == thread_id,
    BriefingAuditLog.event_type == "email_received",
    BriefingAuditLog.created_at >= one_hour_ago,
).count()
if parse_count >= 10:
    logger.warning("Rate limit: >10 parses/hour on thread %s", thread_id)
    return {"status": "rate_limited"}

# Max 50 replies per LO per day
from database.models.user import User
today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0)
lo_reply_count = db.query(BriefingAuditLog).filter(
    BriefingAuditLog.organization_id == thread.organization_id,
    BriefingAuditLog.event_type == "email_received",
    BriefingAuditLog.created_at >= today_start,
).join(BriefingThread, BriefingAuditLog.thread_id == BriefingThread.id).filter(
    BriefingThread.user_id == thread.user_id,
).count()
if lo_reply_count >= 50:
    logger.warning("Rate limit: >50 replies/day for user %s", thread.user_id)
    return {"status": "rate_limited"}
```

### Fix B: PII redactor on reply bodies (§10.1)

In `services/briefing_thread_service.py`, in `record_inbound_message`, redact before storing:

```python
from services.briefing_audit_service import _redact_pii

def record_inbound_message(self, thread, message_id, body):
    redacted_body = _redact_pii({"body": body}).get("body", body)
    if thread.state in ("AWAITING_REPLY", "CLARIFICATION_SENT"):
        thread.lo_reply_raw = redacted_body
    elif thread.state == "AWAITING_APPROVAL":
        thread.lo_approval_raw = redacted_body
    # ... rest unchanged
```

Note: The parser still receives the un-redacted body for accurate extraction. Only the stored copy is redacted.

### Fix C: 4-hour expiry timezone handling (§13 gap #5)

In `services/briefing_thread_service.py`, `create_thread`, compute expiry as local+4h→UTC:

```python
from zoneinfo import ZoneInfo

def create_thread(self, user_id, morning_briefing_id, briefing_items, user_timezone="America/New_York"):
    now_utc = datetime.now(timezone.utc)
    user_tz = ZoneInfo(user_timezone)
    now_local = now_utc.astimezone(user_tz)
    expires_local = now_local + timedelta(hours=EXPIRY_HOURS)
    expires_utc = expires_local.astimezone(timezone.utc)
    # ... use expires_utc as thread.expires_at
```

### Fix D: Override-fail fallback copy (§15 decision #3)

In Task 18 (`_process_reply_async`), when override validation fails, render the fallback in the confirmation:

```python
# After running preflight on each override:
if not preflight["passed"] and override:
    tasks_for_confirmation.append({
        "number": item_num,
        "summary": item.get("summary", ""),
        "action_description": f"⚠️ I can't {override.instruction_delta} — {preflight['reason']}. Fall back to {item.get('next_best_action', 'email')}, or skip?",
        "confidence": parsed.confidence,
        "risk_level": "medium",
        "needs_decision": True,  # Flag for confirmation renderer
    })
```

Answering the fallback question does NOT consume a modification cycle.

### Fix E: MANUAL_REVIEW notification

In `services/briefing_thread_service.py`, when `transition()` escalates to MANUAL_REVIEW, the caller should send a notification email. Add a return value:

```python
def transition(self, thread, new_state):
    # ... after setting thread.state = "MANUAL_REVIEW":
    return "MANUAL_REVIEW"  # Signal to caller to send notification
```

The caller in Task 18 checks for this and sends: "Your briefing conversation has been escalated for manual review after 3 modification cycles."

### Fix F: Manager reply handling

Already handled in Task 18: `is_authorized_sender()` returns False for manager emails, and the audit log entry is created with `actor=f"unauthorized:{msg['sender']}"`. No state change occurs. This matches spec decision #4 (log and ignore).

### Fix G: Carryover flow

In Task 20 (`generate_user_briefing`), when building `briefing_items` for a new thread, pull carryover tasks from yesterday:

```python
from database.models.briefing_thread import BriefingTask
from datetime import date

carryover_tasks = db.query(BriefingTask).filter(
    BriefingTask.organization_id == org_id,
    BriefingTask.status == "carryover",
    BriefingTask.carryover_target_date == date.today(),
).join(BriefingThread).filter(
    BriefingThread.user_id == user_id,
).all()

for ct in carryover_tasks:
    briefing_items.insert(0, {
        "summary": ct.briefing_item_summary,
        "next_best_action": ct.action_type,
        "action_params": ct.action_params,
        "carryover": True,
    })
```

And in Task 18, mark non-handled items as carryover:

```python
for item_num in range(1, len(thread.briefing_items) + 1):
    if item_num not in handled:
        item = thread.briefing_items[item_num - 1]
        if not item.get("carryover"):  # Don't carry over twice
            task = BriefingTask(
                thread_id=thread.id,
                organization_id=thread.organization_id,
                briefing_item_number=item_num,
                briefing_item_summary=item.get("summary", ""),
                action_type=item.get("next_best_action", "create_crm_task"),
                status="carryover",
                carryover_target_date=date.today() + timedelta(days=1),
            )
            db.add(task)
```

---

## Appendix: Deployment Checklist

This is not a task — it's a reference for deployment.

- [ ] Run migration: `python migrations/create_briefing_thread_tables.py`
- [ ] Set environment variables: `ARIA_GRAPH_TENANT_ID`, `ARIA_GRAPH_CLIENT_ID`, `ARIA_GRAPH_CLIENT_SECRET`
- [ ] Verify DNS: SPF, DKIM, DMARC for `perenniaai.com` MAIL FROM alignment
- [ ] Set `interactive_briefing_enabled = True` on pilot org(s)
- [ ] Monitor: `poll_briefing_replies` task execution in Celery Flower
- [ ] Monitor: `briefing_audit_log` table growth
- [ ] Monitor: Graph API rate limits on `aria@perenniaai.com` mailbox
