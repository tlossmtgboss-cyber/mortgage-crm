# Morning Briefing Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the platform's first autonomous agent loop — a scheduled system that generates personalized, role-aware morning briefings for every active user, delivered via email and an in-app Dashboard card.

**Architecture:** Celery Beat dispatches every 15 minutes, checking which users need briefings based on timezone. Individual Celery tasks gather pipeline data via SQL, call Haiku for a priorities narrative, render an HTML email, send via NotificationService, and save to a `morning_briefings` table for in-app display. Three briefing levels (individual, manager, leadership) determined by `permission_role` + `manager_id` hierarchy.

**Tech Stack:** FastAPI, SQLAlchemy, Celery + Redis, Anthropic API (Haiku), SendGrid, React

**Spec:** `docs/superpowers/specs/2026-03-24-morning-briefing-agent-design.md`

---

## File Structure

```
backend/
  database/models/morning_briefing.py     — NEW: MorningBriefing SQLAlchemy model
  database/models/core.py                 — MODIFY: add manager_id + relationship to User
  database/models/__init__.py             — MODIFY: add MorningBriefing import/re-export
  migrations/add_morning_briefings.py     — NEW: migration script
  services/morning_briefing_service.py    — NEW: data gathering, AI, rendering
  templates/morning_briefing_email.py     — NEW: HTML email template builder
  tasks/morning_briefing_tasks.py         — NEW: Celery tasks (dispatch, generate, cleanup)
  tasks/celery_app.py                     — MODIFY: add include, beat_schedule, routing
  routes/briefing_routes.py               — NEW: API endpoints
  routes/inline_legacy_routes.py          — MODIFY: register briefing router
  tests/test_morning_briefing_service.py  — NEW: service tests
  tests/test_morning_briefing_tasks.py    — NEW: task tests
  tests/test_briefing_routes.py           — NEW: route tests

frontend/
  src/components/dashboard/MorningBriefingCard.js   — NEW: Dashboard card
  src/components/dashboard/MorningBriefingCard.css   — NEW: Card styles
  src/pages/Dashboard.js                             — MODIFY: add briefing card
  src/pages/Settings.js                              — MODIFY: add briefing section
```

---

## Task 1: Migration & Data Model

**Files:**
- Create: `backend/database/models/morning_briefing.py`
- Modify: `backend/database/models/core.py`
- Modify: `backend/database/models/__init__.py`
- Create: `backend/migrations/add_morning_briefings.py`

- [ ] **Step 1: Create MorningBriefing model**

Create `backend/database/models/morning_briefing.py`:

```python
"""
Morning Briefing Model

Stores daily autonomous briefings generated for each user.
One briefing per user per day, with level-specific data.
"""
from sqlalchemy import (
    Column, Integer, String, Date, Text, Boolean, DateTime, ForeignKey, Index,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from datetime import datetime, timezone

from db import Base


class MorningBriefing(Base):
    __tablename__ = "morning_briefings"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    briefing_date = Column(Date, nullable=False)
    briefing_level = Column(String, nullable=False, default="individual")  # individual, manager, leadership
    status = Column(String, nullable=False, default="pending")  # pending, generating, delivered, failed
    briefing_data = Column(JSONB, nullable=True)
    team_data = Column(JSONB, nullable=True)
    ai_narrative = Column(Text, nullable=True)
    html_content = Column(Text, nullable=True)
    email_sent_at = Column(DateTime(timezone=True), nullable=True)
    email_message_id = Column(String, nullable=True)
    viewed_in_app_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    organization = relationship("Organization", foreign_keys=[organization_id])

    __table_args__ = (
        UniqueConstraint("user_id", "briefing_date", name="uq_user_briefing_date"),
        Index("ix_briefing_date_status", "briefing_date", "status"),
        Index("ix_org_briefing_date", "organization_id", "briefing_date"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "briefing_date": self.briefing_date.isoformat() if self.briefing_date else None,
            "briefing_level": self.briefing_level,
            "status": self.status,
            "ai_narrative": self.ai_narrative,
            "viewed_in_app": self.viewed_in_app_at is not None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
```

- [ ] **Step 2: Add manager_id to User model**

In `backend/database/models/core.py`, add to the User class columns (after `branch_id`):

```python
    # Organizational hierarchy
    manager_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    # Briefing preferences
    briefing_enabled = Column(Boolean, default=True)
    briefing_hour = Column(Integer, default=7)  # 0-23 in user's timezone
```

Add to the User class relationships:

```python
    # Manager hierarchy (self-referential)
    manager = relationship("User", remote_side="User.id", foreign_keys="User.manager_id",
                           backref="direct_reports")
```

- [ ] **Step 3: Add MorningBriefing to model exports**

In `backend/database/models/__init__.py`, add to the imports:

```python
from .morning_briefing import MorningBriefing
```

And add `"MorningBriefing"` to the `__all__` list.

- [ ] **Step 4: Create migration script**

Create `backend/migrations/add_morning_briefings.py`:

```python
"""
Migration: Add Morning Briefings

Creates morning_briefings table and adds manager_id, briefing_enabled,
briefing_hour columns to users table.
"""
import sys
sys.path.append('..')

from sqlalchemy import create_engine, text
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./mortgage_crm.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)


def run_migration():
    """Create morning_briefings table and add user columns."""

    sql_commands = [
        # 1. Add manager_id to users
        """
        ALTER TABLE users ADD COLUMN IF NOT EXISTS manager_id INTEGER REFERENCES users(id);
        """,
        # 2. Add index on manager_id
        """
        CREATE INDEX IF NOT EXISTS ix_users_manager_id ON users(manager_id);
        """,
        # 3. Add briefing preferences to users
        """
        ALTER TABLE users ADD COLUMN IF NOT EXISTS briefing_enabled BOOLEAN DEFAULT TRUE;
        """,
        """
        ALTER TABLE users ADD COLUMN IF NOT EXISTS briefing_hour INTEGER DEFAULT 7;
        """,
        # 4. Create morning_briefings table
        """
        CREATE TABLE IF NOT EXISTS morning_briefings (
            id SERIAL PRIMARY KEY,
            organization_id INTEGER NOT NULL REFERENCES organizations(id),
            user_id INTEGER NOT NULL REFERENCES users(id),
            briefing_date DATE NOT NULL,
            briefing_level VARCHAR(20) NOT NULL DEFAULT 'individual',
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            briefing_data JSONB,
            team_data JSONB,
            ai_narrative TEXT,
            html_content TEXT,
            email_sent_at TIMESTAMP WITH TIME ZONE,
            email_message_id VARCHAR(255),
            viewed_in_app_at TIMESTAMP WITH TIME ZONE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_user_briefing_date UNIQUE (user_id, briefing_date)
        );
        """,
        # 5. Indexes
        """
        CREATE INDEX IF NOT EXISTS ix_briefing_date_status
            ON morning_briefings(briefing_date, status);
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_org_briefing_date
            ON morning_briefings(organization_id, briefing_date);
        """,
    ]

    with engine.connect() as conn:
        for cmd in sql_commands:
            try:
                conn.execute(text(cmd))
                logger.info(f"Executed: {cmd.strip()[:60]}...")
            except Exception as e:
                logger.warning(f"Skipped (may already exist): {e}")
        conn.commit()

    logger.info("Morning briefings migration complete")


if __name__ == "__main__":
    run_migration()
```

- [ ] **Step 5: Verify model imports**

Run: `cd /Users/timothyloss/my-project/mortgage-crm/backend && .venv/bin/python3 -c "from database.models import MorningBriefing, User; print('MorningBriefing:', MorningBriefing.__tablename__); print('manager_id:', hasattr(User, 'manager_id'))"`

Expected: Both print successfully.

- [ ] **Step 6: Commit**

```bash
git add backend/database/models/morning_briefing.py backend/database/models/core.py backend/database/models/__init__.py backend/migrations/add_morning_briefings.py
git commit -m "feat: add MorningBriefing model, manager_id on User, migration"
```

---

## Task 2: Morning Briefing Service — Individual Data Gathering

**Files:**
- Create: `backend/services/morning_briefing_service.py`
- Create: `backend/tests/test_morning_briefing_service.py`

- [ ] **Step 1: Write failing tests for individual data gathering**

Create `backend/tests/test_morning_briefing_service.py`:

```python
"""Tests for morning briefing service."""
import pytest
from unittest.mock import MagicMock, patch
from datetime import date, datetime, timezone, timedelta
from services.morning_briefing_service import MorningBriefingService


class TestBriefingLevelDetection:
    """Test briefing level determination."""

    def test_individual_level_for_sales_role(self):
        user = MagicMock()
        user.permission_role = "sales"
        user.direct_reports = []
        assert MorningBriefingService.determine_level(user) == "individual"

    def test_manager_level_with_direct_reports(self):
        user = MagicMock()
        user.permission_role = "management"
        user.direct_reports = [MagicMock()]
        assert MorningBriefingService.determine_level(user) == "manager"

    def test_leadership_level(self):
        user = MagicMock()
        user.permission_role = "leadership"
        user.direct_reports = []
        assert MorningBriefingService.determine_level(user) == "leadership"

    def test_admin_is_leadership(self):
        user = MagicMock()
        user.permission_role = "admin"
        user.direct_reports = []
        assert MorningBriefingService.determine_level(user) == "leadership"

    def test_branch_manager_without_reports_is_individual(self):
        user = MagicMock()
        user.permission_role = "branch_manager"
        user.direct_reports = []
        assert MorningBriefingService.determine_level(user) == "individual"


class TestHealthIndicator:
    """Test team member health calculation."""

    def test_green_no_issues(self):
        assert MorningBriefingService.compute_health(at_risk=0, stale_leads=0, sla_breach=False) == "green"

    def test_yellow_some_risk(self):
        assert MorningBriefingService.compute_health(at_risk=1, stale_leads=2, sla_breach=False) == "yellow"

    def test_red_sla_breach(self):
        assert MorningBriefingService.compute_health(at_risk=0, stale_leads=0, sla_breach=True) == "red"

    def test_red_many_at_risk(self):
        assert MorningBriefingService.compute_health(at_risk=3, stale_leads=0, sla_breach=False) == "red"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/timothyloss/my-project/mortgage-crm/backend && .venv/bin/python3 -m pytest tests/test_morning_briefing_service.py -v 2>&1 | head -30`

Expected: FAIL — `ModuleNotFoundError: No module named 'services.morning_briefing_service'`

- [ ] **Step 3: Create the service with level detection and health logic**

Create `backend/services/morning_briefing_service.py`:

```python
"""
Morning Briefing Service

Gathers pipeline data, generates AI narratives, and renders briefings
for individual contributors, managers, and leadership.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# SLA targets in days (same as CLAUDE.md pipeline tools)
SLA_TARGETS = {
    "APPLICATION": 3,
    "DISCLOSED": 7,
    "SUBMITTED": 2,
    "UNDERWRITING": 5,
    "UW_RECEIVED": 5,
    "APPROVED": 3,
    "CONDITIONAL_APPROVAL": 3,
    "CLEAR_TO_CLOSE": 3,
    "CTC": 3,
    "DOCS_OUT": 5,
}

TERMINAL_STAGES = (
    "FUNDED", "CANCELLED", "DENIED", "DEAD", "WITHDRAWN", "DOES_NOT_QUALIFY",
)

LEADERSHIP_ROLES = ("leadership", "admin", "site_admin", "platform_admin")
MANAGER_ROLES = ("management", "branch_manager", "regional_manager")


@dataclass
class BriefingContext:
    """All data needed to generate a briefing."""
    user_id: int
    user_name: str
    organization_id: int
    briefing_date: date
    level: str  # individual, manager, leadership

    # Individual data
    pipeline: Dict[str, Any] = field(default_factory=dict)
    at_risk: List[Dict[str, Any]] = field(default_factory=list)
    stale_leads: List[Dict[str, Any]] = field(default_factory=list)
    appointments: List[Dict[str, Any]] = field(default_factory=list)
    conditions: List[Dict[str, Any]] = field(default_factory=list)
    yesterday: Dict[str, Any] = field(default_factory=dict)

    # Team/org data (manager and leadership only)
    team: Optional[Dict[str, Any]] = None


class MorningBriefingService:
    """Generates morning briefings at all hierarchy levels."""

    # ------------------------------------------------------------------
    # Level detection
    # ------------------------------------------------------------------

    @staticmethod
    def determine_level(user: Any) -> str:
        """Determine briefing level from user role and direct reports."""
        role = getattr(user, "permission_role", "sales") or "sales"

        if role in LEADERSHIP_ROLES:
            return "leadership"

        reports = getattr(user, "direct_reports", None) or []
        if role in MANAGER_ROLES and len(reports) > 0:
            return "manager"

        return "individual"

    @staticmethod
    def compute_health(at_risk: int = 0, stale_leads: int = 0, sla_breach: bool = False) -> str:
        """Compute health indicator for a team member or branch."""
        if sla_breach or at_risk >= 3:
            return "red"
        if at_risk >= 1 or stale_leads >= 3:
            return "yellow"
        return "green"

    # ------------------------------------------------------------------
    # Individual data gathering (Level 1)
    # ------------------------------------------------------------------

    def gather_individual_data(
        self, db: Session, user_id: int, org_id: int, briefing_date: date, user_tz: str,
    ) -> Dict[str, Any]:
        """Run 6 queries for individual-level briefing data."""
        today = briefing_date
        yesterday = today - timedelta(days=1)
        week_ahead = today + timedelta(days=7)
        three_days = today + timedelta(days=3)

        pipeline = self._query_pipeline_snapshot(db, user_id, org_id, week_ahead)
        at_risk = self._query_at_risk_loans(db, user_id, org_id, three_days)
        stale_leads = self._query_stale_leads(db, user_id, org_id, today)
        appointments = self._query_todays_appointments(db, user_id, org_id, today, user_tz)
        conditions = self._query_pending_conditions(db, user_id, org_id, today)
        yesterday_activity = self._query_yesterday_activity(db, user_id, org_id, yesterday)

        return {
            "pipeline": pipeline,
            "at_risk": at_risk,
            "stale_leads": stale_leads,
            "appointments": appointments,
            "conditions": conditions,
            "yesterday": yesterday_activity,
        }

    def _query_pipeline_snapshot(self, db: Session, user_id: int, org_id: int, week_ahead: date) -> Dict:
        """Active loans count, volume, stage breakdown, closing soon."""
        terminal = ", ".join(f"'{s}'" for s in TERMINAL_STAGES)
        try:
            summary = db.execute(sa_text(f"""
                SELECT
                    COUNT(*) as total_count,
                    COALESCE(SUM(amount), 0) as total_volume,
                    COUNT(CASE WHEN closing_date <= :week_ahead THEN 1 END) as closing_soon
                FROM loans
                WHERE loan_officer_id = :uid AND organization_id = :oid
                  AND (stage IS NULL OR UPPER(stage) NOT IN ({terminal}))
            """), {"uid": user_id, "oid": org_id, "week_ahead": week_ahead}).fetchone()

            stages = db.execute(sa_text(f"""
                SELECT UPPER(stage) as stage, COUNT(*) as cnt
                FROM loans
                WHERE loan_officer_id = :uid AND organization_id = :oid
                  AND (stage IS NULL OR UPPER(stage) NOT IN ({terminal}))
                GROUP BY UPPER(stage)
                ORDER BY cnt DESC
            """), {"uid": user_id, "oid": org_id}).fetchall()

            return {
                "active_count": summary[0] or 0,
                "total_volume": float(summary[1] or 0),
                "closing_soon": summary[2] or 0,
                "by_stage": {row[0]: row[1] for row in stages},
            }
        except Exception as e:
            logger.error("Pipeline snapshot query failed: %s", e)
            return {"active_count": 0, "total_volume": 0, "closing_soon": 0, "by_stage": {}}

    def _query_at_risk_loans(self, db: Session, user_id: int, org_id: int, three_days: date) -> List[Dict]:
        """Loans with SLA breaches, expiring locks, or stagnation."""
        terminal = ", ".join(f"'{s}'" for s in TERMINAL_STAGES)
        try:
            rows = db.execute(sa_text(f"""
                SELECT
                    id, loan_number, borrower_name, UPPER(stage) as stage,
                    stage_changed_at, lock_expiration_date,
                    EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - stage_changed_at)) / 86400 as days_in_stage
                FROM loans
                WHERE loan_officer_id = :uid AND organization_id = :oid
                  AND (stage IS NULL OR UPPER(stage) NOT IN ({terminal}))
                  AND (
                    lock_expiration_date <= :three_days
                    OR EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - stage_changed_at)) / 86400 > 10
                  )
                ORDER BY
                    CASE WHEN lock_expiration_date <= :three_days THEN 0 ELSE 1 END,
                    days_in_stage DESC
                LIMIT 10
            """), {"uid": user_id, "oid": org_id, "three_days": three_days}).fetchall()

            results = []
            for r in rows:
                stage = r[3] or ""
                days = float(r[6] or 0)
                sla_target = SLA_TARGETS.get(stage, 7)
                reason = []
                if r[5] and r[5] <= three_days:
                    reason.append(f"Lock expires {r[5].strftime('%m/%d') if hasattr(r[5], 'strftime') else r[5]}")
                if days > sla_target:
                    reason.append(f"{days:.0f} days in {stage} (SLA: {sla_target})")
                if days > 10 and not reason:
                    reason.append(f"No movement in {days:.0f} days")

                results.append({
                    "loan_id": r[0],
                    "loan_number": r[1],
                    "borrower": r[2] or "Unknown",
                    "stage": stage,
                    "days_in_stage": round(days, 1),
                    "reason": "; ".join(reason),
                })
            return results
        except Exception as e:
            logger.error("At-risk query failed: %s", e)
            return []

    def _query_stale_leads(self, db: Session, user_id: int, org_id: int, today: date) -> List[Dict]:
        """Leads with no recent contact, prioritizing high-score leads."""
        try:
            rows = db.execute(sa_text("""
                SELECT
                    id, first_name, last_name, ai_score, last_contact,
                    EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - last_contact)) / 86400 as days_silent
                FROM leads
                WHERE owner_id = :uid AND organization_id = :oid
                  AND last_contact IS NOT NULL
                  AND (
                    (ai_score >= 70 AND last_contact < CURRENT_DATE - INTERVAL '3 days')
                    OR last_contact < CURRENT_DATE - INTERVAL '7 days'
                  )
                ORDER BY ai_score DESC NULLS LAST, days_silent DESC
                LIMIT 10
            """), {"uid": user_id, "oid": org_id}).fetchall()

            return [
                {
                    "lead_id": r[0],
                    "name": f"{r[1] or ''} {r[2] or ''}".strip() or "Unknown",
                    "score": r[3],
                    "days_silent": round(float(r[5] or 0), 0),
                }
                for r in rows
            ]
        except Exception as e:
            logger.error("Stale leads query failed: %s", e)
            return []

    def _query_todays_appointments(
        self, db: Session, user_id: int, org_id: int, today: date, user_tz: str,
    ) -> List[Dict]:
        """Today's appointments for this user."""
        try:
            rows = db.execute(sa_text("""
                SELECT
                    sa.id, sa.attendee_name, sa.title,
                    sa.scheduled_start AT TIME ZONE 'UTC' AT TIME ZONE :tz as local_start
                FROM scheduler_appointments sa
                WHERE sa.assigned_user_id = :uid AND sa.organization_id = :oid
                  AND (sa.scheduled_start AT TIME ZONE 'UTC' AT TIME ZONE :tz)::date = :today
                  AND sa.status NOT IN ('cancelled', 'no_show')
                ORDER BY sa.scheduled_start
            """), {"uid": user_id, "oid": org_id, "tz": user_tz, "today": today}).fetchall()

            return [
                {
                    "id": r[0],
                    "attendee": r[1] or "Unknown",
                    "type": r[2] or "Appointment",
                    "time": r[3].strftime("%-I:%M %p") if r[3] else "",
                }
                for r in rows
            ]
        except Exception as e:
            logger.error("Appointments query failed: %s", e)
            return []

    def _query_pending_conditions(self, db: Session, user_id: int, org_id: int, today: date) -> List[Dict]:
        """Open compliance alerts on this user's loans."""
        try:
            rows = db.execute(sa_text("""
                SELECT
                    ca.id, ca.title, ca.severity, ca.deadline_date, l.loan_number
                FROM compliance_alerts ca
                JOIN loans l ON l.id = ca.loan_id
                WHERE l.loan_officer_id = :uid AND l.organization_id = :oid
                  AND ca.status = 'open'
                ORDER BY
                    CASE WHEN ca.deadline_date < :today THEN 0 ELSE 1 END,
                    ca.deadline_date ASC NULLS LAST
                LIMIT 10
            """), {"uid": user_id, "oid": org_id, "today": today}).fetchall()

            return [
                {
                    "title": r[1],
                    "severity": r[2],
                    "past_due": bool(r[3] and r[3] < today),
                    "loan_number": r[4],
                }
                for r in rows
            ]
        except Exception as e:
            logger.error("Conditions query failed: %s", e)
            return []

    def _query_yesterday_activity(self, db: Session, user_id: int, org_id: int, yesterday: date) -> Dict:
        """Loans funded, new pipeline, lead conversions from yesterday."""
        try:
            result = db.execute(sa_text("""
                SELECT
                    COUNT(CASE WHEN funded_date = :yesterday THEN 1 END) as funded,
                    COUNT(CASE WHEN created_at::date = :yesterday THEN 1 END) as new_loans
                FROM loans
                WHERE loan_officer_id = :uid AND organization_id = :oid
            """), {"uid": user_id, "oid": org_id, "yesterday": yesterday}).fetchone()

            lead_conversions = db.execute(sa_text("""
                SELECT COUNT(*) FROM leads
                WHERE owner_id = :uid AND organization_id = :oid
                  AND stage = 'Converted' AND updated_at::date = :yesterday
            """), {"uid": user_id, "oid": org_id, "yesterday": yesterday}).fetchone()

            return {
                "funded": result[0] or 0,
                "new_loans": result[1] or 0,
                "conversions": lead_conversions[0] if lead_conversions else 0,
            }
        except Exception as e:
            logger.error("Yesterday activity query failed: %s", e)
            return {"funded": 0, "new_loans": 0, "conversions": 0}

    # ------------------------------------------------------------------
    # Manager data gathering (Level 2)
    # ------------------------------------------------------------------

    def gather_manager_data(self, db: Session, user_id: int, org_id: int, briefing_date: date) -> Dict:
        """Gather subordinate roll-up data for manager briefing."""
        today = briefing_date
        three_days = today + timedelta(days=3)

        try:
            # Get direct reports
            reports = db.execute(sa_text("""
                SELECT id, first_name, last_name
                FROM users
                WHERE manager_id = :uid AND is_active = TRUE AND organization_id = :oid
            """), {"uid": user_id, "oid": org_id}).fetchall()

            if not reports:
                return {"members": [], "attention_items": []}

            report_ids = [r[0] for r in reports]
            report_names = {r[0]: f"{r[1] or ''} {r[2] or ''}".strip() for r in reports}
            id_list = ", ".join(str(i) for i in report_ids)
            terminal = ", ".join(f"'{s}'" for s in TERMINAL_STAGES)

            # Team pipeline summary per report
            team_loans = db.execute(sa_text(f"""
                SELECT
                    loan_officer_id,
                    COUNT(*) as loan_count,
                    COALESCE(SUM(amount), 0) as volume,
                    AVG(EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - stage_changed_at)) / 86400) as avg_days
                FROM loans
                WHERE loan_officer_id IN ({id_list}) AND organization_id = :oid
                  AND (stage IS NULL OR UPPER(stage) NOT IN ({terminal}))
                GROUP BY loan_officer_id
            """), {"oid": org_id}).fetchall()

            loan_map = {r[0]: {"count": r[1], "volume": float(r[2] or 0), "avg_days": float(r[3] or 0)} for r in team_loans}

            # At-risk per report
            at_risk_counts = db.execute(sa_text(f"""
                SELECT loan_officer_id, COUNT(*) as cnt,
                    BOOL_OR(EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - stage_changed_at)) / 86400 >
                        CASE UPPER(stage)
                            WHEN 'APPLICATION' THEN 3 WHEN 'DISCLOSED' THEN 7
                            WHEN 'SUBMITTED' THEN 2 WHEN 'UW_RECEIVED' THEN 5
                            WHEN 'APPROVED' THEN 3 WHEN 'CLEAR_TO_CLOSE' THEN 3
                            WHEN 'DOCS_OUT' THEN 5 ELSE 7
                        END
                    ) as has_sla_breach
                FROM loans
                WHERE loan_officer_id IN ({id_list}) AND organization_id = :oid
                  AND (stage IS NULL OR UPPER(stage) NOT IN ({terminal}))
                  AND (
                    lock_expiration_date <= :three_days
                    OR EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - stage_changed_at)) / 86400 > 10
                  )
                GROUP BY loan_officer_id
            """), {"oid": org_id, "three_days": three_days}).fetchall()

            risk_map = {r[0]: {"count": r[1], "sla_breach": bool(r[2])} for r in at_risk_counts}

            # Stale leads per report
            stale_counts = db.execute(sa_text(f"""
                SELECT owner_id, COUNT(*) as cnt
                FROM leads
                WHERE owner_id IN ({id_list}) AND organization_id = :oid
                  AND last_contact IS NOT NULL
                  AND last_contact < CURRENT_DATE - INTERVAL '7 days'
                GROUP BY owner_id
            """), {"oid": org_id}).fetchall()

            stale_map = {r[0]: r[1] for r in stale_counts}

            # Build members list
            members = []
            for uid in report_ids:
                loans_info = loan_map.get(uid, {"count": 0, "volume": 0, "avg_days": 0})
                risk_info = risk_map.get(uid, {"count": 0, "sla_breach": False})
                stale = stale_map.get(uid, 0)

                members.append({
                    "user_id": uid,
                    "name": report_names[uid],
                    "loan_count": loans_info["count"],
                    "volume": loans_info["volume"],
                    "at_risk_count": risk_info["count"],
                    "stale_lead_count": stale,
                    "health": self.compute_health(
                        at_risk=risk_info["count"],
                        stale_leads=stale,
                        sla_breach=risk_info["sla_breach"],
                    ),
                })

            # Top attention items across all reports
            attention = db.execute(sa_text(f"""
                SELECT
                    l.loan_officer_id, l.loan_number, l.borrower_name,
                    UPPER(l.stage) as stage, l.lock_expiration_date,
                    EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - l.stage_changed_at)) / 86400 as days
                FROM loans l
                WHERE l.loan_officer_id IN ({id_list}) AND l.organization_id = :oid
                  AND (l.stage IS NULL OR UPPER(l.stage) NOT IN ({terminal}))
                  AND (
                    l.lock_expiration_date <= :three_days
                    OR EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - l.stage_changed_at)) / 86400 > 10
                  )
                ORDER BY
                    CASE WHEN l.lock_expiration_date <= :three_days THEN 0 ELSE 1 END,
                    days DESC
                LIMIT 5
            """), {"oid": org_id, "three_days": three_days}).fetchall()

            attention_items = []
            for r in attention:
                lo_name = report_names.get(r[0], "Unknown")
                issue_parts = []
                if r[4] and r[4] <= three_days:
                    issue_parts.append(f"{r[2] or 'Unknown'} loan lock expires soon")
                elif float(r[5] or 0) > 10:
                    issue_parts.append(f"{r[2] or 'Unknown'} loan stalled {float(r[5]):.0f} days in {r[3]}")

                attention_items.append({
                    "user_name": lo_name,
                    "loan_number": r[1],
                    "issue": "; ".join(issue_parts) if issue_parts else f"{r[2]} loan needs attention",
                    "severity": "high" if r[4] and r[4] <= three_days else "medium",
                })

            return {"members": members, "attention_items": attention_items}

        except Exception as e:
            logger.error("Manager data gathering failed: %s", e)
            return {"members": [], "attention_items": []}

    # ------------------------------------------------------------------
    # Leadership data gathering (Level 3)
    # ------------------------------------------------------------------

    def gather_leadership_data(self, db: Session, org_id: int, briefing_date: date) -> Dict:
        """Gather org-wide roll-up for leadership briefing."""
        today = briefing_date
        three_days = today + timedelta(days=3)
        week_ago = today - timedelta(days=7)
        two_weeks_ago = today - timedelta(days=14)
        terminal = ", ".join(f"'{s}'" for s in TERMINAL_STAGES)

        try:
            # Org active pipeline snapshot (excludes terminal stages)
            org_snap = db.execute(sa_text(f"""
                SELECT
                    COUNT(*) as total,
                    COALESCE(SUM(amount), 0) as volume
                FROM loans
                WHERE organization_id = :oid
                  AND (stage IS NULL OR UPPER(stage) NOT IN ({terminal}))
            """), {"oid": org_id}).fetchone()

            # Funded counts (separate query — funded IS a terminal stage)
            funded_snap = db.execute(sa_text("""
                SELECT
                    COUNT(CASE WHEN funded_date >= :week_ago THEN 1 END) as funded_this_week,
                    COUNT(CASE WHEN funded_date >= :two_weeks_ago AND funded_date < :week_ago THEN 1 END) as funded_last_week
                FROM loans
                WHERE organization_id = :oid AND funded_date >= :two_weeks_ago
            """), {"oid": org_id, "week_ago": week_ago, "two_weeks_ago": two_weeks_ago}).fetchone()

            # Branch comparison
            branches = db.execute(sa_text(f"""
                SELECT
                    COALESCE(b.name, 'Unassigned') as branch_name,
                    COUNT(l.id) as loan_count,
                    COALESCE(SUM(l.amount), 0) as volume,
                    AVG(EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - l.stage_changed_at)) / 86400) as avg_days,
                    COUNT(CASE WHEN l.lock_expiration_date <= :three_days
                        OR EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - l.stage_changed_at)) / 86400 > 10
                        THEN 1 END) as at_risk
                FROM loans l
                JOIN users u ON u.id = l.loan_officer_id
                LEFT JOIN branches b ON b.id = u.branch_id
                WHERE l.organization_id = :oid
                  AND (l.stage IS NULL OR UPPER(l.stage) NOT IN ({terminal}))
                GROUP BY b.name
                ORDER BY volume DESC
            """), {"oid": org_id, "three_days": three_days}).fetchall()

            branch_list = []
            for r in branches:
                at_risk = r[4] or 0
                avg_days = float(r[3] or 0)
                branch_list.append({
                    "name": r[0],
                    "loan_count": r[1],
                    "volume": float(r[2] or 0),
                    "avg_days_in_stage": round(avg_days, 1),
                    "at_risk_count": at_risk,
                    "health": self.compute_health(at_risk=at_risk, stale_leads=0, sla_breach=avg_days > 10),
                })

            # Top org risks
            top_risks = db.execute(sa_text(f"""
                SELECT
                    l.loan_number, l.borrower_name, UPPER(l.stage) as stage,
                    l.lock_expiration_date,
                    EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - l.stage_changed_at)) / 86400 as days,
                    CONCAT(u.first_name, ' ', u.last_name) as lo_name,
                    COALESCE(b.name, 'Unassigned') as branch_name
                FROM loans l
                JOIN users u ON u.id = l.loan_officer_id
                LEFT JOIN branches b ON b.id = u.branch_id
                WHERE l.organization_id = :oid
                  AND (l.stage IS NULL OR UPPER(l.stage) NOT IN ({terminal}))
                  AND (
                    l.lock_expiration_date <= :three_days
                    OR EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - l.stage_changed_at)) / 86400 > 10
                  )
                ORDER BY
                    CASE WHEN l.lock_expiration_date <= :three_days THEN 0 ELSE 1 END,
                    days DESC
                LIMIT 10
            """), {"oid": org_id, "three_days": three_days}).fetchall()

            risks = []
            for r in top_risks:
                issue = ""
                if r[3] and r[3] <= three_days:
                    issue = f"Lock expires {r[3].strftime('%m/%d') if hasattr(r[3], 'strftime') else r[3]}"
                else:
                    issue = f"{float(r[4]):.0f} days in {r[2]}"
                risks.append({
                    "loan_number": r[0],
                    "borrower": r[1] or "Unknown",
                    "lo_name": r[5],
                    "branch": r[6],
                    "issue": issue,
                })

            funded_this_week = funded_snap[0] or 0
            funded_last_week = funded_snap[1] or 0

            return {
                "org_snapshot": {
                    "active_count": org_snap[0] or 0,
                    "total_volume": float(org_snap[1] or 0),
                    "funded_this_week": funded_this_week,
                    "funded_last_week": funded_last_week,
                    "funded_trend": "up" if funded_this_week > funded_last_week else (
                        "down" if funded_this_week < funded_last_week else "flat"
                    ),
                },
                "branches": branch_list,
                "top_risks": risks,
            }

        except Exception as e:
            logger.error("Leadership data gathering failed: %s", e)
            return {"org_snapshot": {}, "branches": [], "top_risks": []}

    # ------------------------------------------------------------------
    # Full briefing context builder
    # ------------------------------------------------------------------

    def build_context(
        self, db: Session, user: Any, briefing_date: date,
    ) -> BriefingContext:
        """Build complete BriefingContext for a user."""
        user_id = user.id
        org_id = user.organization_id
        user_tz = getattr(user, "timezone", None) or "America/New_York"
        user_name = getattr(user, "full_name", None) or f"{user.first_name or ''} {user.last_name or ''}".strip()
        level = self.determine_level(user)

        ctx = BriefingContext(
            user_id=user_id,
            user_name=user_name,
            organization_id=org_id,
            briefing_date=briefing_date,
            level=level,
        )

        # Individual data (all levels get this)
        individual = self.gather_individual_data(db, user_id, org_id, briefing_date, user_tz)
        ctx.pipeline = individual["pipeline"]
        ctx.at_risk = individual["at_risk"]
        ctx.stale_leads = individual["stale_leads"]
        ctx.appointments = individual["appointments"]
        ctx.conditions = individual["conditions"]
        ctx.yesterday = individual["yesterday"]

        # Manager roll-up
        if level == "manager":
            ctx.team = self.gather_manager_data(db, user_id, org_id, briefing_date)

        # Leadership roll-up
        if level == "leadership":
            ctx.team = self.gather_leadership_data(db, org_id, briefing_date)

        return ctx
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/timothyloss/my-project/mortgage-crm/backend && .venv/bin/python3 -m pytest tests/test_morning_briefing_service.py -v 2>&1 | tail -20`

Expected: All 9 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/services/morning_briefing_service.py backend/tests/test_morning_briefing_service.py
git commit -m "feat: add morning briefing service with individual/manager/leadership data gathering"
```

---

## Task 3: AI Narrative Generation

**Files:**
- Modify: `backend/services/morning_briefing_service.py`

- [ ] **Step 1: Add AI narrative generation methods to MorningBriefingService**

Append to `backend/services/morning_briefing_service.py`:

```python
    # ------------------------------------------------------------------
    # AI narrative generation
    # ------------------------------------------------------------------

    INDIVIDUAL_SYSTEM_PROMPT = (
        "You are a senior mortgage pipeline advisor. Given the loan officer's "
        "current pipeline data, write exactly 3 prioritized actions for today. "
        "Each priority should name a specific loan/lead, explain WHY it's urgent, "
        "and state the ONE action to take. Be direct — no pleasantries, no hedging. "
        "Write in second person (\"You should...\"). Keep total response under 200 words."
    )

    MANAGER_SYSTEM_PROMPT = (
        "You are a senior mortgage operations advisor. Given a manager's personal "
        "pipeline and their team's performance data, write exactly 3 priorities. "
        "Priority 1 should address the most urgent team issue (a subordinate with "
        "at-risk loans or neglected leads). Priorities 2-3 can be personal pipeline "
        "items or team items — pick whichever is most urgent. Name specific people "
        "and loans. Write in second person. Keep total response under 250 words."
    )

    LEADERSHIP_SYSTEM_PROMPT = (
        "You are a chief strategy advisor for a mortgage lending operation. Given "
        "the organization's pipeline data and branch performance, write exactly 3 "
        "strategic priorities. Focus on trends, branch performance gaps, and "
        "org-wide risks. Name specific branches and top-risk loans. Do not drill "
        "into individual LO performance — that's for their managers. Write in "
        "second person. Keep total response under 250 words."
    )

    def generate_narrative(self, ctx: BriefingContext) -> Optional[str]:
        """Generate AI narrative using Anthropic Haiku."""
        try:
            import anthropic
        except ImportError:
            logger.warning("anthropic package not installed; skipping AI narrative")
            return None

        system_prompt = {
            "individual": self.INDIVIDUAL_SYSTEM_PROMPT,
            "manager": self.MANAGER_SYSTEM_PROMPT,
            "leadership": self.LEADERSHIP_SYSTEM_PROMPT,
        }.get(ctx.level, self.INDIVIDUAL_SYSTEM_PROMPT)

        user_prompt = self._format_context_for_ai(ctx)

        try:
            import os
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                logger.warning("ANTHROPIC_API_KEY not set; skipping AI narrative")
                return None

            client = anthropic.Anthropic(api_key=api_key)
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=350,
                temperature=0.3,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            return response.content[0].text
        except Exception as e:
            logger.error("AI narrative generation failed: %s", e)
            return None

    def _format_context_for_ai(self, ctx: BriefingContext) -> str:
        """Format BriefingContext as structured text for the AI prompt."""
        lines = [f"Briefing for {ctx.user_name} on {ctx.briefing_date.isoformat()}"]
        lines.append("")

        # Pipeline
        p = ctx.pipeline
        lines.append(f"PIPELINE: {p.get('active_count', 0)} active loans, "
                      f"${p.get('total_volume', 0):,.0f} volume, "
                      f"{p.get('closing_soon', 0)} closing this week")
        if p.get("by_stage"):
            for stage, cnt in p["by_stage"].items():
                lines.append(f"  {stage}: {cnt} loans")

        # At-risk
        if ctx.at_risk:
            lines.append("")
            lines.append("AT-RISK LOANS:")
            for loan in ctx.at_risk:
                lines.append(f"  - {loan['borrower']} ({loan['loan_number']}): {loan['reason']}")

        # Stale leads
        if ctx.stale_leads:
            lines.append("")
            lines.append("STALE LEADS:")
            for lead in ctx.stale_leads:
                lines.append(f"  - {lead['name']} (score {lead['score']}): {lead['days_silent']:.0f} days silent")

        # Appointments
        if ctx.appointments:
            lines.append("")
            lines.append("TODAY'S APPOINTMENTS:")
            for appt in ctx.appointments:
                lines.append(f"  - {appt['time']} — {appt['attendee']}, {appt['type']}")

        # Conditions
        if ctx.conditions:
            lines.append("")
            lines.append("PENDING CONDITIONS:")
            for cond in ctx.conditions:
                pd = " (PAST DUE)" if cond.get("past_due") else ""
                lines.append(f"  - {cond['title']} on {cond['loan_number']}{pd}")

        # Yesterday
        y = ctx.yesterday
        if any(y.get(k, 0) > 0 for k in ("funded", "new_loans", "conversions")):
            lines.append("")
            lines.append(f"YESTERDAY: {y.get('funded', 0)} funded, "
                          f"{y.get('new_loans', 0)} new pipeline, "
                          f"{y.get('conversions', 0)} lead conversions")

        # Team data (manager)
        if ctx.level == "manager" and ctx.team:
            lines.append("")
            lines.append("TEAM STATUS:")
            for m in ctx.team.get("members", []):
                lines.append(f"  - {m['name']}: {m['loan_count']} loans, "
                              f"${m['volume']:,.0f}, health: {m['health']}, "
                              f"{m['at_risk_count']} at-risk")
            if ctx.team.get("attention_items"):
                lines.append("TEAM ATTENTION NEEDED:")
                for item in ctx.team["attention_items"]:
                    lines.append(f"  - {item['user_name']}: {item['issue']}")

        # Org data (leadership)
        if ctx.level == "leadership" and ctx.team:
            snap = ctx.team.get("org_snapshot", {})
            lines.append("")
            lines.append(f"ORG OVERVIEW: {snap.get('active_count', 0)} active loans, "
                          f"${snap.get('total_volume', 0):,.0f} pipeline, "
                          f"{snap.get('funded_this_week', 0)} funded this week "
                          f"({'↑' if snap.get('funded_trend') == 'up' else '↓' if snap.get('funded_trend') == 'down' else '→'} "
                          f"vs {snap.get('funded_last_week', 0)} last week)")
            if ctx.team.get("branches"):
                lines.append("BRANCHES:")
                for b in ctx.team["branches"]:
                    lines.append(f"  - {b['name']}: {b['loan_count']} loans, "
                                  f"${b['volume']:,.0f}, health: {b['health']}")
            if ctx.team.get("top_risks"):
                lines.append("TOP ORG RISKS:")
                for r in ctx.team["top_risks"]:
                    lines.append(f"  - {r['borrower']} ({r['branch']}, LO: {r['lo_name']}): {r['issue']}")

        return "\n".join(lines)
```

- [ ] **Step 2: Commit**

```bash
git add backend/services/morning_briefing_service.py
git commit -m "feat: add AI narrative generation with level-specific prompts"
```

---

## Task 4: Email Template

**Files:**
- Create: `backend/templates/morning_briefing_email.py`

- [ ] **Step 1: Create HTML email template builder**

Create `backend/templates/morning_briefing_email.py`:

```python
"""
Morning Briefing Email Template

Renders BriefingContext into responsive HTML email with inline CSS.
Level-aware: individual, manager, and leadership sections.
"""
from __future__ import annotations
from datetime import date
from typing import Any, Dict, List, Optional


def render_briefing_email(
    user_name: str,
    briefing_date: date,
    level: str,
    ai_narrative: Optional[str],
    pipeline: Dict[str, Any],
    at_risk: List[Dict],
    stale_leads: List[Dict],
    appointments: List[Dict],
    conditions: List[Dict],
    yesterday: Dict[str, Any],
    team: Optional[Dict[str, Any]] = None,
    app_url: str = "https://app.perenniaai.com",
) -> str:
    """Render complete briefing email HTML."""
    date_str = briefing_date.strftime("%B %d, %Y")
    short_date = briefing_date.strftime("%b %d")

    active = pipeline.get("active_count", 0)
    volume = pipeline.get("total_volume", 0)

    if level == "leadership" and team:
        subject_detail = f"${volume / 1_000_000:.1f}M pipeline"
    elif level == "manager" and team:
        member_count = len(team.get("members", []))
        subject_detail = f"{member_count} team members"
    else:
        subject_detail = f"{active} active loans"

    sections = []

    # AI narrative
    if ai_narrative:
        sections.append(_section_priorities(ai_narrative))
    else:
        sections.append(_section_priorities_unavailable())

    sections.append(_divider())

    # Personal pipeline (all levels)
    if active > 0 or level == "individual":
        sections.append(_section_pipeline(pipeline))

    # At-risk
    if at_risk:
        sections.append(_section_at_risk(at_risk))

    # Stale leads
    if stale_leads:
        sections.append(_section_stale_leads(stale_leads))

    # Appointments
    if appointments:
        sections.append(_section_appointments(appointments))

    # Conditions
    if conditions:
        sections.append(_section_conditions(conditions))

    # Team section (manager)
    if level == "manager" and team:
        sections.append(_divider())
        sections.append(_section_team(team))

    # Org section (leadership)
    if level == "leadership" and team:
        sections.append(_divider())
        sections.append(_section_org(team))

    body = "\n".join(sections)

    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#f4f4f7;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f7;padding:24px 0;">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:8px;overflow:hidden;max-width:600px;width:100%;">

<!-- Header -->
<tr><td style="background:linear-gradient(135deg,#218d8d,#1a7070);padding:28px 32px;">
  <h1 style="margin:0;color:#ffffff;font-size:20px;font-weight:600;">Good morning, {user_name}</h1>
  <p style="margin:6px 0 0;color:rgba(255,255,255,0.8);font-size:13px;">{date_str}</p>
</td></tr>

<!-- Content -->
<tr><td style="padding:24px 32px 32px;">
{body}
</td></tr>

<!-- CTA -->
<tr><td style="padding:0 32px 32px;" align="center">
  <a href="{app_url}/dashboard" style="display:inline-block;background:#218d8d;color:#ffffff;padding:12px 32px;border-radius:6px;text-decoration:none;font-weight:600;font-size:14px;">Open Perennia</a>
</td></tr>

<!-- Footer -->
<tr><td style="padding:16px 32px;border-top:1px solid #e8e8ed;background:#fafafa;">
  <p style="margin:0;color:#8888a0;font-size:11px;text-align:center;">
    Adjust or disable morning briefings in <a href="{app_url}/settings" style="color:#218d8d;">Settings</a>
  </p>
</td></tr>

</table>
</td></tr>
</table>
</body>
</html>"""


def _section_priorities(narrative: str) -> str:
    # Convert numbered items to styled HTML
    lines = narrative.strip().split("\n")
    items_html = ""
    for line in lines:
        line = line.strip()
        if line:
            items_html += f'<p style="margin:8px 0;color:#1a1a2a;font-size:14px;line-height:1.6;">{line}</p>\n'

    return f"""
<h2 style="margin:0 0 12px;color:#218d8d;font-size:15px;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;">Top 3 Priorities</h2>
{items_html}"""


def _section_priorities_unavailable() -> str:
    return """
<h2 style="margin:0 0 12px;color:#218d8d;font-size:15px;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;">Your Pipeline</h2>
<p style="margin:0;color:#8888a0;font-size:13px;font-style:italic;">AI priorities unavailable today — here's your pipeline data.</p>"""


def _divider() -> str:
    return '<hr style="border:none;border-top:1px solid #e8e8ed;margin:20px 0;">'


def _section_pipeline(pipeline: Dict) -> str:
    active = pipeline.get("active_count", 0)
    volume = pipeline.get("total_volume", 0)
    closing = pipeline.get("closing_soon", 0)
    by_stage = pipeline.get("by_stage", {})

    stage_rows = ""
    for stage, cnt in by_stage.items():
        stage_rows += f'<tr><td style="padding:6px 12px;border-bottom:1px solid #f0f0f4;font-size:13px;color:#4a4a5a;">{stage}</td><td style="padding:6px 12px;border-bottom:1px solid #f0f0f4;font-size:13px;color:#1a1a2a;font-weight:600;text-align:right;">{cnt}</td></tr>\n'

    return f"""
<h2 style="margin:0 0 8px;color:#218d8d;font-size:15px;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;">Pipeline Snapshot</h2>
<p style="margin:0 0 12px;color:#4a4a5a;font-size:14px;">{active} active loans &middot; ${volume:,.0f} volume &middot; {closing} closing this week</p>
<table width="100%" cellpadding="0" cellspacing="0" style="background:#fafafa;border-radius:6px;overflow:hidden;">
<tr><th style="padding:8px 12px;text-align:left;font-size:11px;color:#8888a0;text-transform:uppercase;border-bottom:1px solid #e8e8ed;">Stage</th><th style="padding:8px 12px;text-align:right;font-size:11px;color:#8888a0;text-transform:uppercase;border-bottom:1px solid #e8e8ed;">Count</th></tr>
{stage_rows}</table>"""


def _section_at_risk(items: List[Dict]) -> str:
    rows = ""
    for item in items:
        rows += f'<li style="margin:4px 0;font-size:13px;color:#4a4a5a;"><strong>{item["borrower"]}</strong> ({item.get("loan_number", "")}) — {item["reason"]}</li>\n'
    return f"""
<h2 style="margin:20px 0 8px;color:#e74c3c;font-size:15px;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;">&#9888; At-Risk ({len(items)} loans)</h2>
<ul style="margin:0;padding-left:20px;">{rows}</ul>"""


def _section_stale_leads(items: List[Dict]) -> str:
    rows = ""
    for item in items:
        rows += f'<li style="margin:4px 0;font-size:13px;color:#4a4a5a;"><strong>{item["name"]}</strong> (score {item.get("score", "?")}) — {item["days_silent"]:.0f} days quiet</li>\n'
    return f"""
<h2 style="margin:20px 0 8px;color:#f39c12;font-size:15px;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;">&#128293; Leads Going Cold ({len(items)})</h2>
<ul style="margin:0;padding-left:20px;">{rows}</ul>"""


def _section_appointments(items: List[Dict]) -> str:
    rows = ""
    for item in items:
        rows += f'<li style="margin:4px 0;font-size:13px;color:#4a4a5a;"><strong>{item["time"]}</strong> — {item["attendee"]}, {item["type"]}</li>\n'
    return f"""
<h2 style="margin:20px 0 8px;color:#218d8d;font-size:15px;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;">&#128197; Today's Appointments ({len(items)})</h2>
<ul style="margin:0;padding-left:20px;">{rows}</ul>"""


def _section_conditions(items: List[Dict]) -> str:
    rows = ""
    for item in items:
        pd = ' <span style="color:#e74c3c;font-weight:700;">PAST DUE</span>' if item.get("past_due") else ""
        rows += f'<li style="margin:4px 0;font-size:13px;color:#4a4a5a;">{item["title"]} on {item.get("loan_number", "")}{pd}</li>\n'
    return f"""
<h2 style="margin:20px 0 8px;color:#8e44ad;font-size:15px;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;">Pending Conditions ({len(items)})</h2>
<ul style="margin:0;padding-left:20px;">{rows}</ul>"""


def _health_dot(health: str) -> str:
    colors = {"green": "#27ae60", "yellow": "#f39c12", "red": "#e74c3c"}
    return f'<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:{colors.get(health, "#ccc")};"></span>'


def _section_team(team: Dict) -> str:
    members = team.get("members", [])
    attention = team.get("attention_items", [])

    member_rows = ""
    for m in members:
        health = _health_dot(m.get("health", "green"))
        detail = ""
        if m.get("at_risk_count", 0) > 0:
            detail = f' &middot; {m["at_risk_count"]} at-risk'
        member_rows += f'''<tr>
<td style="padding:8px 12px;border-bottom:1px solid #f0f0f4;font-size:13px;">{health} {m["name"]}</td>
<td style="padding:8px 12px;border-bottom:1px solid #f0f0f4;font-size:13px;text-align:right;">{m.get("loan_count", 0)}</td>
<td style="padding:8px 12px;border-bottom:1px solid #f0f0f4;font-size:13px;text-align:right;">${m.get("volume", 0):,.0f}</td>
<td style="padding:8px 12px;border-bottom:1px solid #f0f0f4;font-size:13px;text-align:right;color:#8888a0;">{m.get("health", "green")}{detail}</td>
</tr>\n'''

    attention_html = ""
    if attention:
        items = ""
        for a in attention:
            items += f'<li style="margin:4px 0;font-size:13px;color:#4a4a5a;"><strong>{a["user_name"]}</strong> — {a["issue"]}</li>\n'
        attention_html = f"""
<h3 style="margin:16px 0 8px;color:#e74c3c;font-size:13px;font-weight:700;text-transform:uppercase;">Team Attention Needed</h3>
<ul style="margin:0;padding-left:20px;">{items}</ul>"""

    return f"""
<h2 style="margin:0 0 12px;color:#218d8d;font-size:15px;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;">Your Team</h2>
<table width="100%" cellpadding="0" cellspacing="0" style="background:#fafafa;border-radius:6px;overflow:hidden;">
<tr>
<th style="padding:8px 12px;text-align:left;font-size:11px;color:#8888a0;text-transform:uppercase;border-bottom:1px solid #e8e8ed;">Name</th>
<th style="padding:8px 12px;text-align:right;font-size:11px;color:#8888a0;text-transform:uppercase;border-bottom:1px solid #e8e8ed;">Loans</th>
<th style="padding:8px 12px;text-align:right;font-size:11px;color:#8888a0;text-transform:uppercase;border-bottom:1px solid #e8e8ed;">Volume</th>
<th style="padding:8px 12px;text-align:right;font-size:11px;color:#8888a0;text-transform:uppercase;border-bottom:1px solid #e8e8ed;">Health</th>
</tr>
{member_rows}</table>
{attention_html}"""


def _section_org(team: Dict) -> str:
    snap = team.get("org_snapshot", {})
    branches = team.get("branches", [])
    risks = team.get("top_risks", [])

    trend_arrow = {"up": "&#8593;", "down": "&#8595;", "flat": "&#8594;"}.get(snap.get("funded_trend", "flat"), "&#8594;")

    branch_rows = ""
    for b in branches:
        health = _health_dot(b.get("health", "green"))
        branch_rows += f'''<tr>
<td style="padding:8px 12px;border-bottom:1px solid #f0f0f4;font-size:13px;">{health} {b["name"]}</td>
<td style="padding:8px 12px;border-bottom:1px solid #f0f0f4;font-size:13px;text-align:right;">{b.get("loan_count", 0)}</td>
<td style="padding:8px 12px;border-bottom:1px solid #f0f0f4;font-size:13px;text-align:right;">${b.get("volume", 0):,.0f}</td>
<td style="padding:8px 12px;border-bottom:1px solid #f0f0f4;font-size:13px;text-align:right;color:#8888a0;">{b.get("health", "green")}</td>
</tr>\n'''

    risk_items = ""
    if risks:
        for r in risks:
            risk_items += f'<li style="margin:4px 0;font-size:13px;color:#4a4a5a;"><strong>{r["borrower"]}</strong> ({r["branch"]}, LO: {r["lo_name"]}) — {r["issue"]}</li>\n'

    risk_section = ""
    if risk_items:
        risk_section = f"""
<h3 style="margin:16px 0 8px;color:#e74c3c;font-size:13px;font-weight:700;text-transform:uppercase;">Top Risks (Org-Wide)</h3>
<ul style="margin:0;padding-left:20px;">{risk_items}</ul>"""

    return f"""
<h2 style="margin:0 0 8px;color:#218d8d;font-size:15px;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;">Organization Overview</h2>
<p style="margin:0 0 16px;color:#4a4a5a;font-size:14px;">
  ${snap.get('total_volume', 0):,.0f} pipeline &middot; {snap.get('active_count', 0)} active loans &middot;
  {snap.get('funded_this_week', 0)} funded this week {trend_arrow} vs {snap.get('funded_last_week', 0)} last week
</p>

<h3 style="margin:0 0 8px;color:#4a4a5a;font-size:13px;font-weight:700;text-transform:uppercase;">Branch Performance</h3>
<table width="100%" cellpadding="0" cellspacing="0" style="background:#fafafa;border-radius:6px;overflow:hidden;">
<tr>
<th style="padding:8px 12px;text-align:left;font-size:11px;color:#8888a0;text-transform:uppercase;border-bottom:1px solid #e8e8ed;">Branch</th>
<th style="padding:8px 12px;text-align:right;font-size:11px;color:#8888a0;text-transform:uppercase;border-bottom:1px solid #e8e8ed;">Loans</th>
<th style="padding:8px 12px;text-align:right;font-size:11px;color:#8888a0;text-transform:uppercase;border-bottom:1px solid #e8e8ed;">Volume</th>
<th style="padding:8px 12px;text-align:right;font-size:11px;color:#8888a0;text-transform:uppercase;border-bottom:1px solid #e8e8ed;">Health</th>
</tr>
{branch_rows}</table>
{risk_section}"""
```

- [ ] **Step 2: Commit**

```bash
git add backend/templates/morning_briefing_email.py
git commit -m "feat: add morning briefing HTML email template with level-aware sections"
```

---

## Task 5: Celery Tasks

**Files:**
- Create: `backend/tasks/morning_briefing_tasks.py`
- Modify: `backend/tasks/celery_app.py`

- [ ] **Step 1: Create Celery tasks**

Create `backend/tasks/morning_briefing_tasks.py`:

```python
"""
Morning Briefing Celery Tasks

Dispatch: runs every 15 min, finds users due for briefings.
Generate: builds one briefing per user (data + AI + email + send).
Cleanup: deletes briefings older than 90 days.
"""
from __future__ import annotations

import logging
import os
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def _get_db_session():
    """Create a fresh DB session for background tasks."""
    from db import SessionLocal
    return SessionLocal()


def _get_all_briefing_candidates(db):
    """Get all active users with briefing_enabled = True."""
    from sqlalchemy import text as sa_text
    rows = db.execute(sa_text("""
        SELECT id, timezone, briefing_hour, permission_role, organization_id
        FROM users
        WHERE is_active = TRUE
          AND COALESCE(briefing_enabled, TRUE) = TRUE
    """)).fetchall()
    return rows


@celery_app.task(name="tasks.morning_briefing_tasks.dispatch_briefings")
def dispatch_briefings():
    """
    Runs every 15 minutes via Beat. Checks which users are due for a briefing
    based on their timezone and briefing_hour.
    """
    from sqlalchemy import text as sa_text

    db = _get_db_session()
    try:
        now_utc = datetime.now(timezone.utc)
        candidates = _get_all_briefing_candidates(db)
        db.close()
        db = None

        enqueued = 0
        individual_idx = 0
        manager_idx = 0

        for row in candidates:
            user_id, user_tz, briefing_hour, perm_role, org_id = (
                row[0], row[1] or "America/New_York", row[2] or 7, row[3] or "sales", row[4],
            )

            try:
                tz = ZoneInfo(user_tz)
            except Exception:
                tz = ZoneInfo("America/New_York")

            local_now = now_utc.astimezone(tz)
            local_hour = local_now.hour
            local_date = local_now.date()

            if local_hour != briefing_hour:
                continue

            # Check if briefing already exists for today
            check_db = _get_db_session()
            try:
                exists = check_db.execute(sa_text("""
                    SELECT 1 FROM morning_briefings
                    WHERE user_id = :uid AND briefing_date = :bdate
                    LIMIT 1
                """), {"uid": user_id, "bdate": local_date}).fetchone()
                check_db.close()

                if exists:
                    continue
            except Exception:
                check_db.close()
                continue

            # Determine level
            is_leadership = perm_role in ("leadership", "admin", "site_admin", "platform_admin")
            is_manager = perm_role in ("management", "branch_manager", "regional_manager")

            if is_leadership:
                level = "leadership"
            elif is_manager:
                # Check if they have direct reports
                rpt_db = _get_db_session()
                try:
                    has_reports = rpt_db.execute(sa_text("""
                        SELECT 1 FROM users
                        WHERE manager_id = :uid AND is_active = TRUE
                        LIMIT 1
                    """), {"uid": user_id}).fetchone()
                    rpt_db.close()
                    level = "manager" if has_reports else "individual"
                except Exception:
                    rpt_db.close()
                    level = "individual"
            else:
                level = "individual"

            # Stagger: individuals first, managers/leadership delayed 5 min
            if level == "individual":
                delay = individual_idx * 2
                individual_idx += 1
            else:
                delay = 300 + manager_idx * 2
                manager_idx += 1

            generate_user_briefing.apply_async(
                args=[user_id, local_date.isoformat(), level],
                countdown=delay,
            )
            enqueued += 1

        logger.info("Briefing dispatch: enqueued %d users", enqueued)
        return {"enqueued": enqueued}

    except Exception as e:
        logger.error("Briefing dispatch failed: %s", e)
        return {"error": str(e)}
    finally:
        if db:
            db.close()


@celery_app.task(
    name="tasks.morning_briefing_tasks.generate_user_briefing",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
    queue="ai_tasks",
)
def generate_user_briefing(self, user_id: int, briefing_date_str: str, briefing_level: str):
    """Generate and deliver a single user's morning briefing."""
    import time
    from sqlalchemy import text as sa_text
    from database.models.morning_briefing import MorningBriefing
    from services.morning_briefing_service import MorningBriefingService
    from templates.morning_briefing_email import render_briefing_email

    start_time = time.time()
    briefing_date = date.fromisoformat(briefing_date_str)

    db = _get_db_session()
    try:
        # Load user with direct_reports
        from database.models import User
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            logger.warning("Briefing: user %d not found", user_id)
            return {"error": "user_not_found"}

        # Check for existing briefing (race condition guard)
        existing = db.query(MorningBriefing).filter(
            MorningBriefing.user_id == user_id,
            MorningBriefing.briefing_date == briefing_date,
        ).first()
        if existing:
            logger.info("Briefing already exists for user %d on %s", user_id, briefing_date_str)
            return {"status": "already_exists"}

        # Create pending record
        briefing = MorningBriefing(
            organization_id=user.organization_id,
            user_id=user_id,
            briefing_date=briefing_date,
            briefing_level=briefing_level,
            status="generating",
        )
        db.add(briefing)
        db.flush()

        # Gather data
        service = MorningBriefingService()
        ctx = service.build_context(db, user, briefing_date)

        briefing.briefing_data = {
            "pipeline": ctx.pipeline,
            "at_risk": ctx.at_risk,
            "stale_leads": ctx.stale_leads,
            "appointments": ctx.appointments,
            "conditions": ctx.conditions,
            "yesterday": ctx.yesterday,
        }
        if ctx.team:
            briefing.team_data = ctx.team

        # Generate AI narrative
        ai_start = time.time()
        narrative = service.generate_narrative(ctx)
        ai_duration = (time.time() - ai_start) * 1000
        briefing.ai_narrative = narrative

        # Render email HTML
        user_name = user.full_name if hasattr(user, "full_name") else (
            f"{user.first_name or ''} {user.last_name or ''}".strip() or "there"
        )
        html = render_briefing_email(
            user_name=user_name,
            briefing_date=briefing_date,
            level=briefing_level,
            ai_narrative=narrative,
            pipeline=ctx.pipeline,
            at_risk=ctx.at_risk,
            stale_leads=ctx.stale_leads,
            appointments=ctx.appointments,
            conditions=ctx.conditions,
            yesterday=ctx.yesterday,
            team=ctx.team,
        )
        briefing.html_content = html

        # Send email
        email_sent = False
        try:
            _send_briefing_email(user.email, user_name, briefing_date, briefing_level, html, ctx.pipeline)
            briefing.email_sent_at = datetime.now(timezone.utc)
            email_sent = True
        except Exception as e:
            logger.error("Briefing email send failed for user %d: %s", user_id, e)

        briefing.status = "delivered" if email_sent else "failed"
        briefing.updated_at = datetime.now(timezone.utc)
        db.commit()

        total_duration = (time.time() - start_time) * 1000
        logger.info(
            "briefing.generate.complete user_id=%d level=%s ai_ms=%.0f total_ms=%.0f email=%s",
            user_id, briefing_level, ai_duration, total_duration, email_sent,
        )

        return {"status": briefing.status, "briefing_id": briefing.id}

    except Exception as e:
        db.rollback()
        logger.error("Briefing generation failed for user %d: %s", user_id, e)
        try:
            self.retry(exc=e)
        except self.MaxRetriesExceededError:
            # Mark as failed after all retries
            try:
                fail_db = _get_db_session()
                fail_briefing = fail_db.query(MorningBriefing).filter(
                    MorningBriefing.user_id == user_id,
                    MorningBriefing.briefing_date == briefing_date,
                ).first()
                if fail_briefing:
                    fail_briefing.status = "failed"
                    fail_briefing.updated_at = datetime.now(timezone.utc)
                    fail_db.commit()
                fail_db.close()
            except Exception:
                pass
            return {"error": str(e)}
    finally:
        db.close()


def _send_briefing_email(
    to_email: str, user_name: str, briefing_date: date,
    level: str, html: str, pipeline: dict,
):
    """Send briefing email via SendGrid / notification service."""
    import sendgrid
    from sendgrid.helpers.mail import Mail, Email, To, Content

    api_key = os.getenv("SENDGRID_API_KEY")
    if not api_key:
        logger.warning("SENDGRID_API_KEY not set; skipping email send")
        return

    active = pipeline.get("active_count", 0)
    volume = pipeline.get("total_volume", 0)
    short_date = briefing_date.strftime("%b %d")

    level_labels = {"individual": f"{active} active loans", "manager": "team briefing", "leadership": f"${volume / 1_000_000:.1f}M pipeline"}
    subject = f"Your Morning Briefing — {short_date} — {level_labels.get(level, '')}"

    from_email = os.getenv("BRIEFING_FROM_EMAIL", "briefing@perenniaai.com")
    from_name = os.getenv("SENDGRID_FROM_NAME", "Perennia AI")

    message = Mail(
        from_email=Email(from_email, from_name),
        to_emails=To(to_email),
        subject=subject,
        html_content=Content("text/html", html),
    )

    sg = sendgrid.SendGridAPIClient(api_key=api_key)
    response = sg.send(message)

    if response.status_code >= 400:
        raise Exception(f"SendGrid returned {response.status_code}")

    logger.info("Briefing email sent to %s (status %d)", to_email, response.status_code)


@celery_app.task(name="tasks.morning_briefing_tasks.cleanup_old_briefings")
def cleanup_old_briefings(retention_days: int = 90):
    """Delete briefings older than retention_days."""
    from sqlalchemy import text as sa_text

    db = _get_db_session()
    try:
        cutoff = date.today() - timedelta(days=retention_days)
        result = db.execute(sa_text("""
            DELETE FROM morning_briefings WHERE briefing_date < :cutoff
        """), {"cutoff": cutoff})
        db.commit()
        deleted = result.rowcount
        logger.info("Briefing cleanup: deleted %d rows older than %s", deleted, cutoff)
        return {"deleted": deleted}
    except Exception as e:
        db.rollback()
        logger.error("Briefing cleanup failed: %s", e)
        return {"error": str(e)}
    finally:
        db.close()
```

- [ ] **Step 2: Update celery_app.py — add to include list**

In `backend/tasks/celery_app.py`, add `"tasks.morning_briefing_tasks"` to the `include` list.

- [ ] **Step 3: Update celery_app.py — add Beat schedule entries**

Add to the `beat_schedule` dict in `backend/tasks/celery_app.py`:

```python
    "morning-briefing-dispatch": {
        "task": "tasks.morning_briefing_tasks.dispatch_briefings",
        "schedule": crontab(minute="0,15,30,45"),
        "options": {"queue": "ai_tasks"},
    },
    "morning-briefing-cleanup": {
        "task": "tasks.morning_briefing_tasks.cleanup_old_briefings",
        "schedule": crontab(hour="3", minute="0", day_of_week="sunday"),
        "options": {"queue": "default"},
    },
```

- [ ] **Step 4: Update celery_app.py — add routing rule**

Add to the `task_routes` dict: `"tasks.morning_briefing_tasks.*": {"queue": "ai_tasks"}`

- [ ] **Step 5: Verify syntax**

Run: `cd /Users/timothyloss/my-project/mortgage-crm/backend && .venv/bin/python3 -c "import ast; ast.parse(open('tasks/morning_briefing_tasks.py').read()); print('OK')"`

Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add backend/tasks/morning_briefing_tasks.py backend/tasks/celery_app.py
git commit -m "feat: add morning briefing Celery tasks (dispatch, generate, cleanup)"
```

---

## Task 6: API Routes

**Files:**
- Create: `backend/routes/briefing_routes.py`
- Modify: `backend/routes/inline_legacy_routes.py`

- [ ] **Step 1: Create briefing routes**

Create `backend/routes/briefing_routes.py`:

```python
"""
Morning Briefing API Routes

GET  /api/v1/briefing/today         — Today's briefing for current user
GET  /api/v1/briefing/history       — Paginated briefing history
POST /api/v1/briefing/generate-now  — Manually trigger a briefing
POST /api/v1/briefing/{id}/viewed   — Mark briefing as viewed in-app
GET  /api/v1/briefing/preferences   — Get briefing preferences
PUT  /api/v1/briefing/preferences   — Update briefing preferences
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/briefing", tags=["Morning Briefing"])


def _get_deps():
    """Lazy import to avoid circular imports."""
    from database.models.morning_briefing import MorningBriefing
    from database.models import User
    return MorningBriefing, User


# --- Schemas ---

class BriefingPreferences(BaseModel):
    briefing_enabled: bool = True
    briefing_hour: int = Field(ge=0, le=23, default=7)


class BriefingResponse(BaseModel):
    class Config:
        from_attributes = True


# --- Dependency stubs (replaced at registration) ---

_get_db = None
_get_current_user = None


def set_dependencies(get_db_func, get_current_user_func):
    global _get_db, _get_current_user
    _get_db = get_db_func
    _get_current_user = get_current_user_func


def get_db():
    if _get_db is None:
        raise RuntimeError("briefing_routes: dependencies not initialized")
    return _get_db()


def get_current_user():
    if _get_current_user is None:
        raise RuntimeError("briefing_routes: dependencies not initialized")
    return _get_current_user()


# --- Routes ---

@router.get("/today")
async def get_today_briefing(db: Session = Depends(get_db),
                              current_user=Depends(get_current_user)):
    """Get current user's briefing for today."""
    MorningBriefing, _ = _get_deps()

    user_tz = getattr(current_user, "timezone", None) or "America/New_York"
    try:
        tz = ZoneInfo(user_tz)
    except Exception:
        tz = ZoneInfo("America/New_York")

    today = datetime.now(tz).date()

    briefing = db.query(MorningBriefing).filter(
        MorningBriefing.user_id == current_user.id,
        MorningBriefing.briefing_date == today,
    ).first()

    if not briefing:
        return Response(status_code=204)  # No briefing yet today

    data = briefing.briefing_data or {}
    team = briefing.team_data

    return {
        "id": briefing.id,
        "briefing_date": briefing.briefing_date.isoformat(),
        "briefing_level": briefing.briefing_level,
        "status": briefing.status,
        "ai_narrative": briefing.ai_narrative,
        "pipeline": data.get("pipeline", {}),
        "at_risk": data.get("at_risk", []),
        "stale_leads": data.get("stale_leads", []),
        "appointments": data.get("appointments", []),
        "conditions": data.get("conditions", []),
        "yesterday": data.get("yesterday", {}),
        "team": team,
        "viewed_in_app": briefing.viewed_in_app_at is not None,
        "created_at": briefing.created_at.isoformat() if briefing.created_at else None,
    }


@router.get("/history")
async def get_briefing_history(
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=30),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get paginated briefing history."""
    MorningBriefing, _ = _get_deps()

    offset = (page - 1) * per_page
    briefings = (
        db.query(MorningBriefing)
        .filter(MorningBriefing.user_id == current_user.id)
        .order_by(MorningBriefing.briefing_date.desc())
        .offset(offset)
        .limit(per_page)
        .all()
    )

    return {
        "page": page,
        "per_page": per_page,
        "items": [
            {
                "id": b.id,
                "briefing_date": b.briefing_date.isoformat(),
                "briefing_level": b.briefing_level,
                "status": b.status,
                "ai_narrative": (b.ai_narrative or "")[:200],
                "viewed_in_app": b.viewed_in_app_at is not None,
            }
            for b in briefings
        ],
    }


@router.post("/generate-now")
async def generate_now(
    force: bool = Query(False),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Manually trigger a briefing for current user."""
    MorningBriefing, _ = _get_deps()
    from services.morning_briefing_service import MorningBriefingService

    user_tz = getattr(current_user, "timezone", None) or "America/New_York"
    try:
        tz = ZoneInfo(user_tz)
    except Exception:
        tz = ZoneInfo("America/New_York")

    today = datetime.now(tz).date()
    level = MorningBriefingService.determine_level(current_user)

    existing = db.query(MorningBriefing).filter(
        MorningBriefing.user_id == current_user.id,
        MorningBriefing.briefing_date == today,
    ).first()

    if existing and not force:
        raise HTTPException(status_code=409, detail="Briefing already exists for today. Use force=true to regenerate.")

    if existing and force:
        db.delete(existing)
        db.commit()

    from tasks.morning_briefing_tasks import generate_user_briefing
    generate_user_briefing.apply_async(args=[current_user.id, today.isoformat(), level])

    return JSONResponse(status_code=202, content={"status": "accepted", "message": "Briefing generation started"})


@router.post("/{briefing_id}/viewed")
async def mark_viewed(
    briefing_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Mark a briefing as viewed in-app."""
    MorningBriefing, _ = _get_deps()

    briefing = db.query(MorningBriefing).filter(
        MorningBriefing.id == briefing_id,
        MorningBriefing.user_id == current_user.id,
    ).first()

    if not briefing:
        raise HTTPException(status_code=404, detail="Briefing not found")

    if not briefing.viewed_in_app_at:
        briefing.viewed_in_app_at = datetime.now(timezone.utc)
        briefing.updated_at = datetime.now(timezone.utc)
        db.commit()

    return {"status": "ok"}


@router.get("/preferences")
async def get_preferences(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get briefing preferences."""
    return {
        "briefing_enabled": getattr(current_user, "briefing_enabled", True) if current_user.briefing_enabled is not None else True,
        "briefing_hour": getattr(current_user, "briefing_hour", 7) or 7,
        "timezone": getattr(current_user, "timezone", "America/New_York"),
    }


@router.put("/preferences")
async def update_preferences(
    prefs: BriefingPreferences,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Update briefing preferences."""
    current_user.briefing_enabled = prefs.briefing_enabled
    current_user.briefing_hour = prefs.briefing_hour
    db.commit()

    return {
        "briefing_enabled": current_user.briefing_enabled,
        "briefing_hour": current_user.briefing_hour,
        "timezone": getattr(current_user, "timezone", "America/New_York"),
    }
```

- [ ] **Step 2: Register routes in inline_legacy_routes.py**

Add this block in `backend/routes/inline_legacy_routes.py` inside the `register_inline_routes` function (after the scheduler routes section):

```python
    # Morning Briefing routes
    try:
        from routes.briefing_routes import router as briefing_router, set_dependencies as set_briefing_deps
        set_briefing_deps(get_db, get_current_user)
        app.include_router(briefing_router, tags=["Morning Briefing"])
        logger.info("Morning Briefing routes loaded")
    except Exception as e:
        logger.warning(f"Morning Briefing routes not loaded: {e}")
```

- [ ] **Step 3: Verify syntax**

Run: `cd /Users/timothyloss/my-project/mortgage-crm/backend && .venv/bin/python3 -c "import ast; ast.parse(open('routes/briefing_routes.py').read()); print('OK')"`

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add backend/routes/briefing_routes.py backend/routes/inline_legacy_routes.py
git commit -m "feat: add morning briefing API routes and register in app"
```

---

## Task 7: Frontend — MorningBriefingCard

**Files:**
- Create: `frontend/src/components/dashboard/MorningBriefingCard.js`
- Create: `frontend/src/components/dashboard/MorningBriefingCard.css`
- Modify: `frontend/src/pages/Dashboard.js`

- [ ] **Step 1: Create MorningBriefingCard component**

Create `frontend/src/components/dashboard/MorningBriefingCard.js`:

```javascript
import React, { useState, useEffect, useCallback } from 'react';
import api from '../../services/api';
import './MorningBriefingCard.css';

export default function MorningBriefingCard() {
  const [briefing, setBriefing] = useState(null);
  const [loading, setLoading] = useState(true);
  const [collapsed, setCollapsed] = useState(() => {
    return localStorage.getItem('briefing_collapsed') === 'true';
  });
  const [dismissed, setDismissed] = useState(() => {
    const d = localStorage.getItem('briefing_dismissed_date');
    return d === new Date().toISOString().split('T')[0];
  });

  const fetchBriefing = useCallback(async () => {
    try {
      const res = await api.get('/api/v1/briefing/today', {
        validateStatus: (status) => status === 200 || status === 204,
      });
      if (res.status === 204) {
        // No briefing yet — nothing to display
      } else if (res.data && res.data.status === 'delivered') {
        setBriefing(res.data);
        // Mark as viewed
        if (!res.data.viewed_in_app) {
          api.post(`/api/v1/briefing/${res.data.id}/viewed`).catch(() => {});
        }
      }
    } catch (err) {
      // Silent failure — briefings are supplementary
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!dismissed) fetchBriefing();
    else setLoading(false);
  }, [dismissed, fetchBriefing]);

  const toggleCollapse = () => {
    const next = !collapsed;
    setCollapsed(next);
    localStorage.setItem('briefing_collapsed', String(next));
  };

  const dismiss = () => {
    setDismissed(true);
    localStorage.setItem('briefing_dismissed_date', new Date().toISOString().split('T')[0]);
  };

  if (loading || dismissed || !briefing) return null;

  const { ai_narrative, pipeline, at_risk, stale_leads, appointments, team, briefing_level } = briefing;

  return (
    <div className="morning-briefing-card">
      <div className="briefing-header" onClick={toggleCollapse}>
        <div className="briefing-title">
          <span className="briefing-icon">&#9728;</span>
          <h3>Morning Briefing</h3>
          <span className="briefing-date">{briefing.briefing_date}</span>
        </div>
        <div className="briefing-actions">
          <button className="briefing-collapse-btn" title={collapsed ? 'Expand' : 'Collapse'}>
            {collapsed ? '▸' : '▾'}
          </button>
          <button className="briefing-dismiss-btn" onClick={(e) => { e.stopPropagation(); dismiss(); }} title="Dismiss for today">
            ✕
          </button>
        </div>
      </div>

      {!collapsed && (
        <div className="briefing-body">
          {/* AI Priorities */}
          {ai_narrative && (
            <div className="briefing-section priorities">
              <h4>Top 3 Priorities</h4>
              <div className="priorities-text">{ai_narrative}</div>
            </div>
          )}

          {/* Pipeline */}
          {pipeline && pipeline.active_count > 0 && (
            <div className="briefing-section">
              <h4>Pipeline</h4>
              <div className="briefing-stats">
                <span><strong>{pipeline.active_count}</strong> active</span>
                <span><strong>${(pipeline.total_volume / 1000000).toFixed(1)}M</strong> volume</span>
                <span><strong>{pipeline.closing_soon}</strong> closing soon</span>
              </div>
            </div>
          )}

          {/* At-Risk */}
          {at_risk && at_risk.length > 0 && (
            <div className="briefing-section at-risk">
              <h4>&#9888; At-Risk ({at_risk.length})</h4>
              <ul>
                {at_risk.slice(0, 3).map((loan, i) => (
                  <li key={i}>
                    <a href={`/loans/${loan.loan_id}`}><strong>{loan.borrower}</strong></a>
                    {' — '}{loan.reason}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Stale Leads */}
          {stale_leads && stale_leads.length > 0 && (
            <div className="briefing-section stale-leads">
              <h4>&#128293; Leads Going Cold ({stale_leads.length})</h4>
              <ul>
                {stale_leads.slice(0, 3).map((lead, i) => (
                  <li key={i}>
                    <a href={`/leads/${lead.lead_id}`}><strong>{lead.name}</strong></a>
                    {' (score '}{lead.score}{') — '}{lead.days_silent} days quiet
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Appointments */}
          {appointments && appointments.length > 0 && (
            <div className="briefing-section">
              <h4>&#128197; Today ({appointments.length})</h4>
              <ul>
                {appointments.map((appt, i) => (
                  <li key={i}><strong>{appt.time}</strong> — {appt.attendee}, {appt.type}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Team Section (Manager) */}
          {briefing_level === 'manager' && team && team.members && (
            <div className="briefing-section team-section">
              <h4>Your Team</h4>
              <table className="briefing-table">
                <thead>
                  <tr><th>Name</th><th>Loans</th><th>Volume</th><th>Health</th></tr>
                </thead>
                <tbody>
                  {team.members.map((m, i) => (
                    <tr key={i}>
                      <td><span className={`health-dot ${m.health}`}></span> {m.name}</td>
                      <td>{m.loan_count}</td>
                      <td>${(m.volume / 1000).toFixed(0)}K</td>
                      <td>{m.health}{m.at_risk_count > 0 ? ` · ${m.at_risk_count} at-risk` : ''}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {team.attention_items && team.attention_items.length > 0 && (
                <div className="attention-items">
                  <h5>Attention Needed</h5>
                  <ul>
                    {team.attention_items.map((item, i) => (
                      <li key={i}><strong>{item.user_name}</strong> — {item.issue}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          {/* Org Section (Leadership) */}
          {briefing_level === 'leadership' && team && team.branches && (
            <div className="briefing-section org-section">
              <h4>Organization Overview</h4>
              {team.org_snapshot && (
                <div className="briefing-stats">
                  <span><strong>{team.org_snapshot.active_count}</strong> active loans</span>
                  <span><strong>${(team.org_snapshot.total_volume / 1000000).toFixed(1)}M</strong> pipeline</span>
                  <span><strong>{team.org_snapshot.funded_this_week}</strong> funded this week</span>
                </div>
              )}
              <table className="briefing-table">
                <thead>
                  <tr><th>Branch</th><th>Loans</th><th>Volume</th><th>Health</th></tr>
                </thead>
                <tbody>
                  {team.branches.map((b, i) => (
                    <tr key={i}>
                      <td><span className={`health-dot ${b.health}`}></span> {b.name}</td>
                      <td>{b.loan_count}</td>
                      <td>${(b.volume / 1000000).toFixed(1)}M</td>
                      <td>{b.health}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Create CSS file**

Create `frontend/src/components/dashboard/MorningBriefingCard.css`:

```css
.morning-briefing-card {
  background: linear-gradient(135deg, #f0fafa, #ffffff);
  border: 1px solid #218d8d33;
  border-radius: 12px;
  margin-bottom: 20px;
  overflow: hidden;
}

.briefing-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  cursor: pointer;
  user-select: none;
}

.briefing-title {
  display: flex;
  align-items: center;
  gap: 10px;
}

.briefing-title h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: #1a1a2a;
}

.briefing-icon { font-size: 20px; }
.briefing-date { font-size: 13px; color: #8888a0; }

.briefing-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

.briefing-collapse-btn,
.briefing-dismiss-btn {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 16px;
  color: #8888a0;
  padding: 4px 8px;
  border-radius: 4px;
}

.briefing-collapse-btn:hover,
.briefing-dismiss-btn:hover {
  background: #f0f0f4;
  color: #4a4a5a;
}

.briefing-body {
  padding: 0 20px 20px;
}

.briefing-section {
  margin-bottom: 16px;
}

.briefing-section h4 {
  margin: 0 0 8px;
  font-size: 13px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: #218d8d;
}

.briefing-section.at-risk h4 { color: #e74c3c; }
.briefing-section.stale-leads h4 { color: #f39c12; }

.briefing-section ul {
  margin: 0;
  padding-left: 18px;
  list-style: disc;
}

.briefing-section li {
  margin: 4px 0;
  font-size: 13px;
  color: #4a4a5a;
  line-height: 1.5;
}

.briefing-section li a {
  color: #218d8d;
  text-decoration: none;
}

.briefing-section li a:hover { text-decoration: underline; }

.priorities-text {
  font-size: 14px;
  line-height: 1.7;
  color: #1a1a2a;
  white-space: pre-line;
}

.briefing-stats {
  display: flex;
  gap: 20px;
  margin-bottom: 8px;
}

.briefing-stats span {
  font-size: 13px;
  color: #4a4a5a;
}

.briefing-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  margin-top: 8px;
}

.briefing-table th {
  text-align: left;
  padding: 8px 12px;
  font-size: 11px;
  text-transform: uppercase;
  color: #8888a0;
  border-bottom: 1px solid #e8e8ed;
  font-weight: 600;
}

.briefing-table td {
  padding: 8px 12px;
  border-bottom: 1px solid #f0f0f4;
  color: #4a4a5a;
}

.health-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-right: 6px;
}

.health-dot.green { background: #27ae60; }
.health-dot.yellow { background: #f39c12; }
.health-dot.red { background: #e74c3c; }

.team-section, .org-section {
  border-top: 1px solid #e8e8ed;
  padding-top: 16px;
}

.attention-items { margin-top: 12px; }
.attention-items h5 {
  margin: 0 0 6px;
  font-size: 12px;
  color: #e74c3c;
  text-transform: uppercase;
  font-weight: 700;
}
```

- [ ] **Step 3: Add MorningBriefingCard to Dashboard.js**

In `frontend/src/pages/Dashboard.js`, add the import near the top:

```javascript
import MorningBriefingCard from '../components/dashboard/MorningBriefingCard';
```

And add the component at the very beginning of the Dashboard's return JSX, before any existing content:

```jsx
<MorningBriefingCard />
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/dashboard/MorningBriefingCard.js frontend/src/components/dashboard/MorningBriefingCard.css frontend/src/pages/Dashboard.js
git commit -m "feat: add MorningBriefingCard component to Dashboard"
```

---

## Task 8: Frontend — Settings Section

**Files:**
- Modify: `frontend/src/pages/Settings.js`

- [ ] **Step 1: Add Morning Briefing section to Settings**

In `frontend/src/pages/Settings.js`, add this component inside the Settings page (find an appropriate location near other notification/preference settings):

```javascript
const MorningBriefingSettings = () => {
  const [prefs, setPrefs] = useState({ briefing_enabled: true, briefing_hour: 7, timezone: '' });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [message, setMessage] = useState(null);

  useEffect(() => {
    const fetchPrefs = async () => {
      try {
        const res = await api.get('/api/v1/briefing/preferences');
        setPrefs(res.data);
      } catch (err) { console.error('Failed to fetch briefing preferences', err); }
      finally { setLoading(false); }
    };
    fetchPrefs();
  }, []);

  const savePrefs = async () => {
    setSaving(true);
    setMessage(null);
    try {
      await api.put('/api/v1/briefing/preferences', {
        briefing_enabled: prefs.briefing_enabled,
        briefing_hour: prefs.briefing_hour,
      });
      setMessage({ type: 'success', text: 'Briefing preferences saved' });
    } catch (err) { setMessage({ type: 'error', text: 'Failed to save preferences' }); }
    finally { setSaving(false); }
  };

  const generateNow = async () => {
    setGenerating(true);
    setMessage(null);
    try {
      await api.post('/api/v1/briefing/generate-now?force=true');
      setMessage({ type: 'success', text: 'Briefing generation started — check your Dashboard in a minute' });
    } catch (err) {
      const detail = err?.response?.data?.detail || 'Failed to generate briefing';
      setMessage({ type: 'error', text: detail });
    }
    finally { setGenerating(false); }
  };

  if (loading) return <div className="settings-section"><h3>Morning Briefing</h3><p>Loading...</p></div>;

  const hourOptions = [];
  for (let h = 5; h <= 11; h++) {
    const label = `${h}:00 AM`;
    hourOptions.push(<option key={h} value={h}>{label}</option>);
  }

  return (
    <div className="settings-section">
      <h3>Morning Briefing</h3>
      <p className="settings-description">Get a daily AI-powered briefing of your pipeline, priorities, and appointments delivered to your email and Dashboard.</p>

      <div className="settings-row">
        <label className="settings-toggle">
          <input
            type="checkbox"
            checked={prefs.briefing_enabled}
            onChange={(e) => setPrefs({ ...prefs, briefing_enabled: e.target.checked })}
          />
          <span>Enable daily briefing</span>
        </label>
      </div>

      <div className="settings-row">
        <label>Delivery time</label>
        <select
          value={prefs.briefing_hour}
          onChange={(e) => setPrefs({ ...prefs, briefing_hour: parseInt(e.target.value) })}
          disabled={!prefs.briefing_enabled}
        >
          {hourOptions}
        </select>
        {prefs.timezone && <span className="settings-hint">in your timezone: {prefs.timezone}</span>}
      </div>

      <div className="settings-row settings-actions">
        <button onClick={savePrefs} disabled={saving} className="btn btn-primary">
          {saving ? 'Saving...' : 'Save Preferences'}
        </button>
        <button onClick={generateNow} disabled={generating || !prefs.briefing_enabled} className="btn btn-secondary">
          {generating ? 'Generating...' : 'Generate Now'}
        </button>
      </div>

      {message && (
        <div className={`settings-message ${message.type}`}>
          {message.text}
        </div>
      )}
    </div>
  );
};
```

Then render `<MorningBriefingSettings />` in the Settings page's JSX in the appropriate tab/section.

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/Settings.js
git commit -m "feat: add Morning Briefing settings section"
```

---

## Task 9: Integration Wiring & Final Verification

**Files:**
- Verify all files with syntax check

- [ ] **Step 1: Verify all Python syntax**

Run: `cd /Users/timothyloss/my-project/mortgage-crm/backend && for f in database/models/morning_briefing.py services/morning_briefing_service.py templates/morning_briefing_email.py tasks/morning_briefing_tasks.py routes/briefing_routes.py migrations/add_morning_briefings.py; do echo -n "$f: "; .venv/bin/python3 -c "import ast; ast.parse(open('$f').read()); print('OK')"; done`

Expected: All files print `OK`.

- [ ] **Step 2: Verify model imports work**

Run: `cd /Users/timothyloss/my-project/mortgage-crm/backend && .venv/bin/python3 -c "from database.models import MorningBriefing; from database.models.core import User; print('Models OK'); print('manager_id' in [c.name for c in User.__table__.columns])"`

Expected: `Models OK` and `True`.

- [ ] **Step 3: Run all new tests**

Run: `cd /Users/timothyloss/my-project/mortgage-crm/backend && .venv/bin/python3 -m pytest tests/test_morning_briefing_service.py -v`

Expected: All tests pass.

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat: complete morning briefing autonomous agent — first autonomous loop

Scheduled Celery Beat task generates personalized, role-aware morning
briefings for every active user. Three levels: individual (personal
pipeline), manager (team roll-up), leadership (org-wide). AI narrative
via Haiku, email via SendGrid, in-app via Dashboard card.

New files: MorningBriefing model, migration, service, Celery tasks,
API routes, email template, React Dashboard card, Settings section."
```
