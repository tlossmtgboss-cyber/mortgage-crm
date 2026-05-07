# Dashboard Snapshot in Morning Briefing — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a full dashboard snapshot to the morning briefing (always included, level-scoped) by extracting dashboard query logic into a shared metrics service.

**Architecture:** Extract 4 existing + 7 new query functions from `dashboard_routes.py` into `services/dashboard_metrics_service.py`. Both the dashboard route and the briefing service call the shared service. Frontend gets a new `DashboardSnapshotSection` component. Email template gets deep-linked dashboard data.

**Tech Stack:** Python/FastAPI, SQLAlchemy ORM, React 18, HTML email templates

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `backend/services/dashboard_metrics_service.py` | **CREATE** | 11 shared query functions with consistent interface |
| `backend/tests/test_dashboard_metrics_service.py` | **CREATE** | Unit tests for all 11 functions |
| `backend/routes/dashboard_routes.py` | **MODIFY** | Replace inline queries with shared service calls |
| `backend/services/morning_briefing_service.py` | **MODIFY** | Add `dashboard_snapshot` field + `_query_dashboard_snapshot()` method |
| `backend/templates/morning_briefing_email.py` | **MODIFY** | Add `_section_dashboard_snapshot()` with deep links |
| `frontend/src/components/briefing/shared.js` | **MODIFY** | Add `DashboardSnapshotSection` component |
| `frontend/src/pages/BriefingPage.js` | **MODIFY** | Render dashboard snapshot section |
| `frontend/src/components/dashboard/MorningBriefingCard.js` | **MODIFY** | Render dashboard snapshot section |

---

### Task 1: Create shared metrics service with extracted functions

**Files:**
- Create: `backend/services/dashboard_metrics_service.py`
- Test: `backend/tests/test_dashboard_metrics_service.py`

- [ ] **Step 1: Write failing test for `calculate_production_metrics()`**

Create `backend/tests/test_dashboard_metrics_service.py`:

```python
"""Tests for dashboard_metrics_service — shared query functions."""
import pytest
from unittest.mock import MagicMock, patch
from datetime import date, datetime, timedelta, timezone


def _make_mock_db():
    """Create a mock DB session with chainable query interface."""
    db = MagicMock()
    query_mock = MagicMock()
    db.query.return_value = query_mock
    query_mock.filter.return_value = query_mock
    query_mock.group_by.return_value = query_mock
    query_mock.order_by.return_value = query_mock
    query_mock.limit.return_value = query_mock
    return db, query_mock


class TestCalculateProductionMetrics:
    def test_returns_default_on_empty_db(self):
        from services.dashboard_metrics_service import calculate_production_metrics
        db, query_mock = _make_mock_db()
        result_row = MagicMock()
        result_row.annual = 0
        result_row.monthly = 0
        result_row.weekly = 0
        result_row.daily = 0
        query_mock.first.return_value = result_row
        result = calculate_production_metrics(db, user_id=1, org_id=1, branch_user_ids=[1])
        assert result["annualActual"] == 0
        assert result["monthlyActual"] == 0
        assert "annualGoal" in result
        assert "monthlyProgress" in result

    def test_scopes_to_branch_user_ids(self):
        from services.dashboard_metrics_service import calculate_production_metrics
        db, query_mock = _make_mock_db()
        result_row = MagicMock()
        result_row.annual = 5
        result_row.monthly = 2
        result_row.weekly = 1
        result_row.daily = 0
        query_mock.first.return_value = result_row
        result = calculate_production_metrics(db, user_id=1, org_id=1, branch_user_ids=[1, 2, 3])
        assert result["annualActual"] == 5
        assert result["monthlyActual"] == 2

    def test_rollback_on_error(self):
        from services.dashboard_metrics_service import calculate_production_metrics
        db, query_mock = _make_mock_db()
        db.query.side_effect = Exception("DB error")
        result = calculate_production_metrics(db, user_id=1, org_id=1, branch_user_ids=[1])
        db.rollback.assert_called_once()
        assert result["annualActual"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/timothyloss/my-project/mortgage-crm/backend && python -m pytest tests/test_dashboard_metrics_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'services.dashboard_metrics_service'`

- [ ] **Step 3: Create `dashboard_metrics_service.py` with all 11 functions**

Create `backend/services/dashboard_metrics_service.py`:

```python
"""
Dashboard Metrics Service — Shared query functions.

Used by both dashboard_routes.py and morning_briefing_service.py.
All functions follow the same scoping convention:
  - branch_user_ids = [user_id] → individual scope
  - branch_user_ids = [id1, id2, ...] → branch/team scope
  - branch_user_ids = None → org-wide (leadership)

Each function has its own try/except with db.rollback() for resilience.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import case, func, extract
from sqlalchemy.orm import Session

from database.enums import LeadStage, LoanStage
from database.models import User, Lead, Loan, Task, AIColleagueAction

logger = logging.getLogger(__name__)

TERMINAL_STAGES = [
    LoanStage.FUNDED, LoanStage.CANCELLED, LoanStage.DENIED,
    LoanStage.DEAD, LoanStage.WITHDRAWN, LoanStage.DOES_NOT_QUALIFY,
    LoanStage.NURTURE,
]

_DEFAULT_PRODUCTION = {
    "annualGoal": 222, "annualActual": 0, "annualProgress": 0,
    "monthlyGoal": 18.5, "monthlyActual": 0, "monthlyProgress": 0,
    "weeklyGoal": 5, "weeklyActual": 0, "weeklyProgress": 0,
    "dailyGoal": 1, "dailyActual": 0, "dailyProgress": 0,
}

_DEFAULT_LEAD_METRICS = {
    "new_today": 0, "avg_contact_time": 1.2, "conversion_rate": 0,
    "hot_leads": 0, "alerts": [],
}

_DEFAULT_TEAM_STATS = {
    "has_team": False, "avg_workload": 0, "backlog": 0,
    "sla_missed": 0, "insights": [],
}

_DEFAULT_EFFICIENCY = {
    "overallScore": 0, "avgTimeToClose": 0, "pullThroughRate": 0,
    "loansFallingBehind": 0, "automationRate": 0,
}

_DEFAULT_PROFITABILITY = {
    "funded_ytd": 0, "total_volume": 0, "avg_loan_size": 0,
    "gain_on_sale": 0, "gain_on_sale_display": "--",
    "revenue_per_loan": 0, "revenue_per_loan_display": "--",
    "avg_points": 0, "cost_per_loan": "--", "net_margin": "--",
    "insights": ["Fund loans to see profitability metrics"],
}


def _apply_scope(query_filters, model_user_col, user_id, org_id, branch_user_ids, model_org_col=None):
    """Add org + user/branch scope filters to a filter list."""
    if model_org_col is not None:
        query_filters.append(model_org_col == org_id)
    if branch_user_ids is not None:
        query_filters.append(model_user_col.in_(branch_user_ids))
    else:
        query_filters.append(model_user_col == user_id)


# =============================================================================
# 1. Production Metrics (goals vs actuals)
# =============================================================================

def calculate_production_metrics(
    db: Session, user_id: int, org_id: int,
    branch_user_ids: Optional[list] = None,
    user_metadata: Optional[dict] = None,
) -> dict:
    """Funded loan counts vs goals (annual/monthly/weekly/daily)."""
    try:
        today = date.today()
        start_of_month = today.replace(day=1)
        start_of_week = today - timedelta(days=today.weekday())

        query_filters = [Loan.stage == LoanStage.FUNDED]
        _apply_scope(query_filters, Loan.loan_officer_id, user_id, org_id, branch_user_ids, Loan.organization_id)

        funded_counts = db.query(
            func.count(case((extract('year', Loan.funded_date) == today.year, 1))).label('annual'),
            func.count(case((Loan.funded_date >= start_of_month, 1))).label('monthly'),
            func.count(case((Loan.funded_date >= start_of_week, 1))).label('weekly'),
            func.count(case((Loan.funded_date == today, 1))).label('daily'),
        ).filter(*query_filters).first()

        annual_actual = funded_counts.annual or 0
        monthly_actual = funded_counts.monthly or 0
        weekly_actual = funded_counts.weekly or 0
        daily_actual = funded_counts.daily or 0

        goals = (user_metadata or {}).get('goals', {})
        annual_goal = goals.get('annualGoal', 222)
        monthly_goal = goals.get('monthlyGoal', 18.5)
        weekly_goal = goals.get('weeklyGoal', 5)
        daily_goal = goals.get('dailyGoal', 1)

        return {
            "annualGoal": annual_goal,
            "annualActual": annual_actual,
            "annualProgress": int(annual_actual / annual_goal * 100) if annual_goal > 0 else 0,
            "monthlyGoal": monthly_goal,
            "monthlyActual": monthly_actual,
            "monthlyProgress": int(monthly_actual / monthly_goal * 100) if monthly_goal > 0 else 0,
            "weeklyGoal": weekly_goal,
            "weeklyActual": weekly_actual,
            "weeklyProgress": int(weekly_actual / weekly_goal * 100) if weekly_goal > 0 else 0,
            "dailyGoal": daily_goal,
            "dailyActual": daily_actual,
            "dailyProgress": int(daily_actual / daily_goal * 100) if daily_goal > 0 else 0,
        }
    except Exception as e:
        logger.error("calculate_production_metrics failed: %s", e)
        db.rollback()
        return dict(_DEFAULT_PRODUCTION)


# =============================================================================
# 2. Pipeline Stats (lead/loan counts by stage bucket)
# =============================================================================

def calculate_pipeline_stats(
    db: Session, user_id: int, org_id: int,
    branch_user_ids: Optional[list] = None,
) -> list:
    """Lead + loan counts per pipeline stage bucket with volumes."""
    try:
        # Lead counts
        lead_filters = []
        _apply_scope(lead_filters, Lead.owner_id, user_id, org_id, branch_user_ids, Lead.organization_id)

        lead_counts = db.query(
            func.count(case((Lead.stage == LeadStage.NEW, 1))).label('new_leads'),
            func.count(case((
                (Lead.stage == LeadStage.NEW) &
                (Lead.created_at < datetime.now(timezone.utc) - timedelta(hours=24)), 1
            ))).label('uncontacted'),
            func.count(case((Lead.stage == LeadStage.PRE_APPROVED, 1))).label('preapproved'),
        ).filter(*lead_filters).first()

        new_leads = lead_counts.new_leads or 0
        uncontacted = lead_counts.uncontacted or 0
        preapproved = lead_counts.preapproved or 0

        # Loan stage buckets
        processing_stages = [LoanStage.APPLICATION, LoanStage.DISCLOSED, LoanStage.PROCESSING]
        underwriting_stages = [LoanStage.SUBMITTED, LoanStage.UNDERWRITING, LoanStage.UW_RECEIVED, LoanStage.CONDITIONAL_APPROVAL]
        ctc_stages = [LoanStage.CTC, LoanStage.CLEAR_TO_CLOSE, LoanStage.APPROVED]
        closing_stages = [LoanStage.CLOSING, LoanStage.DOCS, LoanStage.DOCS_OUT]

        loan_filters = [Loan.stage.notin_(TERMINAL_STAGES)]
        _apply_scope(loan_filters, Loan.loan_officer_id, user_id, org_id, branch_user_ids, Loan.organization_id)

        pipeline_agg = db.query(
            func.count(case((Loan.stage.in_(processing_stages), 1))).label('processing_count'),
            func.sum(case((Loan.stage.in_(processing_stages), Loan.amount), else_=0)).label('processing_volume'),
            func.count(case(((Loan.stage.in_(processing_stages)) & (Loan.days_in_stage > 14), 1))).label('processing_alerts'),
            func.count(case((Loan.stage.in_(underwriting_stages), 1))).label('uw_count'),
            func.sum(case((Loan.stage.in_(underwriting_stages), Loan.amount), else_=0)).label('uw_volume'),
            func.count(case((Loan.stage == LoanStage.SUSPENDED, 1))).label('uw_alerts'),
            func.count(case((Loan.stage.in_(ctc_stages), 1))).label('ctc_count'),
            func.sum(case((Loan.stage.in_(ctc_stages), Loan.amount), else_=0)).label('ctc_volume'),
            func.count(case((Loan.stage.in_(closing_stages), 1))).label('closing_count'),
            func.sum(case((Loan.stage.in_(closing_stages), Loan.amount), else_=0)).label('closing_volume'),
        ).filter(*loan_filters).first()

        # Funded this month
        start_of_month = date.today().replace(day=1)
        funded_filters = [Loan.stage == LoanStage.FUNDED, Loan.funded_date >= start_of_month]
        _apply_scope(funded_filters, Loan.loan_officer_id, user_id, org_id, branch_user_ids, Loan.organization_id)
        funded_data = db.query(
            func.count(Loan.id).label('count'),
            func.sum(Loan.amount).label('volume'),
        ).filter(*funded_filters).first()

        return [
            {"id": "new", "name": "New Leads", "count": new_leads, "alerts": uncontacted, "alert_text": "follow-ups needed" if uncontacted > 0 else "", "volume": None},
            {"id": "preapproved", "name": "Pre-Approved", "count": preapproved, "alerts": 0, "alert_text": "", "volume": None},
            {"id": "processing", "name": "In Processing", "count": pipeline_agg.processing_count or 0, "alerts": pipeline_agg.processing_alerts or 0, "alert_text": "delayed" if (pipeline_agg.processing_alerts or 0) > 0 else "", "volume": int(pipeline_agg.processing_volume or 0)},
            {"id": "underwriting", "name": "In Underwriting", "count": pipeline_agg.uw_count or 0, "alerts": pipeline_agg.uw_alerts or 0, "alert_text": "suspended" if (pipeline_agg.uw_alerts or 0) > 0 else "", "volume": int(pipeline_agg.uw_volume or 0)},
            {"id": "ctc", "name": "Clear to Close", "count": pipeline_agg.ctc_count or 0, "alerts": 0, "alert_text": "", "volume": int(pipeline_agg.ctc_volume or 0)},
            {"id": "closing", "name": "Closing", "count": pipeline_agg.closing_count or 0, "alerts": 0, "alert_text": "", "volume": int(pipeline_agg.closing_volume or 0)},
            {"id": "funded", "name": "Funded This Month", "count": funded_data.count or 0, "alerts": 0, "alert_text": "", "volume": int(funded_data.volume or 0)},
        ]
    except Exception as e:
        logger.error("calculate_pipeline_stats failed: %s", e)
        db.rollback()
        return []


# =============================================================================
# 3. Lead Metrics
# =============================================================================

def calculate_lead_metrics(
    db: Session, user_id: int, org_id: int,
    branch_user_ids: Optional[list] = None,
    lookback_days: int = 30,
) -> dict:
    """Lead counts, conversion rate, hot leads, average contact time."""
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0)

        lead_filters = [Lead.created_at >= cutoff]
        _apply_scope(lead_filters, Lead.owner_id, user_id, org_id, branch_user_ids, Lead.organization_id)

        metrics = db.query(
            func.count(Lead.id).label('total_leads'),
            func.count(case((Lead.created_at >= today_start, 1))).label('new_today'),
            func.count(case(((Lead.ai_score >= 80) & (Lead.stage.in_([LeadStage.NEW, LeadStage.ATTEMPTED_CONTACT])), 1))).label('hot_leads'),
            func.count(case(((Lead.ai_score >= 75) & (Lead.stage == LeadStage.ATTEMPTED_CONTACT), 1))).label('high_intent'),
        ).filter(*lead_filters).first()

        total_leads = metrics.total_leads or 1
        new_today = metrics.new_today or 0
        hot_leads = metrics.hot_leads or 0
        high_intent = metrics.high_intent or 0

        loan_filters = []
        _apply_scope(loan_filters, Loan.loan_officer_id, user_id, org_id, branch_user_ids, Loan.organization_id)
        applications = db.query(func.count(Loan.id)).filter(*loan_filters).scalar() or 0
        conversion_rate = int(applications / total_leads * 100) if total_leads > 0 else 0

        contact_filters = [Lead.first_contact_attempt_date.isnot(None), Lead.created_at.isnot(None)]
        _apply_scope(contact_filters, Lead.owner_id, user_id, org_id, branch_user_ids, Lead.organization_id)
        avg_contact = db.query(
            func.avg(func.extract('epoch', Lead.first_contact_attempt_date - Lead.created_at) / 3600)
        ).filter(*contact_filters).scalar()
        avg_contact_time = round(float(avg_contact), 1) if avg_contact else 1.2

        uncontacted_filters = [Lead.stage == LeadStage.NEW, Lead.created_at < datetime.now(timezone.utc) - timedelta(hours=24)]
        _apply_scope(uncontacted_filters, Lead.owner_id, user_id, org_id, branch_user_ids, Lead.organization_id)
        uncontacted = db.query(func.count(Lead.id)).filter(*uncontacted_filters).scalar() or 0

        alerts = []
        if uncontacted > 0:
            alerts.append(f"{uncontacted} leads haven't been contacted in 24 hours.")
        if high_intent > 0:
            alerts.append(f"{high_intent} leads showed high buying intent.")

        return {
            "new_today": new_today,
            "avg_contact_time": avg_contact_time,
            "conversion_rate": conversion_rate,
            "hot_leads": hot_leads,
            "alerts": alerts,
        }
    except Exception as e:
        logger.error("calculate_lead_metrics failed: %s", e)
        db.rollback()
        return dict(_DEFAULT_LEAD_METRICS)


# =============================================================================
# 4. Profitability
# =============================================================================

def calculate_profitability(
    db: Session, user_id: int, org_id: int,
    branch_user_ids: Optional[list] = None,
) -> dict:
    """YTD funded volume, avg loan size, gain on sale."""
    try:
        start_of_year = date.today().replace(month=1, day=1)
        prof_filters = [Loan.stage == LoanStage.FUNDED, Loan.funded_date >= start_of_year]
        _apply_scope(prof_filters, Loan.loan_officer_id, user_id, org_id, branch_user_ids, Loan.organization_id)

        result = db.query(
            func.count(Loan.id).label('funded_count'),
            func.sum(Loan.amount).label('total_volume'),
            func.avg(Loan.amount).label('avg_loan_size'),
            func.sum(Loan.origination_fee).label('total_origination'),
            func.avg(Loan.origination_fee).label('avg_origination'),
            func.avg(Loan.points).label('avg_points'),
        ).filter(*prof_filters).first()

        funded = result.funded_count or 0
        volume = round(result.total_volume or 0, 2)
        avg_size = round(result.avg_loan_size or 0, 2)
        avg_orig = round(result.avg_origination or 0, 2)
        avg_points = round(result.avg_points or 0, 4)

        gain_bps = int(avg_orig / avg_size * 10000) if avg_size > 0 and avg_orig > 0 else 0

        prof = {
            "funded_ytd": funded,
            "total_volume": volume,
            "avg_loan_size": avg_size,
            "gain_on_sale": gain_bps,
            "gain_on_sale_display": f"{gain_bps} bps" if gain_bps > 0 else "--",
            "revenue_per_loan": round(avg_orig, 2) if avg_orig > 0 else 0,
            "revenue_per_loan_display": f"${avg_orig:,.0f}" if avg_orig > 0 else "--",
            "avg_points": round(avg_points, 3),
            "cost_per_loan": "--",
            "net_margin": f"{gain_bps} bps" if gain_bps > 0 else "--",
            "insights": [],
        }
        if funded > 0:
            prof["insights"].append(f"{funded} loans funded YTD totaling ${volume:,.0f}")
        if avg_size > 0:
            prof["insights"].append(f"Average loan size: ${avg_size:,.0f}")
        if gain_bps > 0:
            prof["insights"].append(f"Avg origination revenue: ${avg_orig:,.0f} per loan ({gain_bps} bps)")
        if not prof["insights"]:
            prof["insights"].append("Fund loans to see profitability metrics")
        return prof
    except Exception as e:
        logger.error("calculate_profitability failed: %s", e)
        db.rollback()
        return dict(_DEFAULT_PROFITABILITY)


# =============================================================================
# 5. Loan Issues
# =============================================================================

def calculate_loan_issues(
    db: Session, user_id: int, org_id: int,
    branch_user_ids: Optional[list] = None,
    limit: int = 10,
) -> list:
    """Top stuck/SLA-behind/lock-expiring loans."""
    try:
        now = datetime.now(timezone.utc)
        issue_filters = [Loan.stage.notin_(TERMINAL_STAGES)]
        _apply_scope(issue_filters, Loan.loan_officer_id, user_id, org_id, branch_user_ids, Loan.organization_id)

        problem_loans = db.query(Loan).filter(
            *issue_filters,
            (Loan.days_in_stage > 14) | (Loan.sla_status == "behind") |
            ((Loan.lock_expiration_date.isnot(None)) & (Loan.lock_expiration_date <= now + timedelta(days=7)))
        ).order_by(Loan.days_in_stage.desc().nullslast()).limit(limit).all()

        return [{
            "id": l.id,
            "borrower_name": l.borrower_name if hasattr(l, 'borrower_name') else f"Loan #{l.id}",
            "stage": l.stage,
            "days_in_stage": l.days_in_stage or 0,
            "sla_status": l.sla_status or "unknown",
            "issue": (
                "Rate lock expiring" if (l.lock_expiration_date and l.lock_expiration_date <= now + timedelta(days=7))
                else ("SLA behind" if l.sla_status == "behind" else f"In stage {l.days_in_stage or 0} days")
            ),
            "amount": round(l.amount, 2) if l.amount else 0,
        } for l in problem_loans]
    except Exception as e:
        logger.error("calculate_loan_issues failed: %s", e)
        db.rollback()
        return []


# =============================================================================
# 6. Team Stats
# =============================================================================

def calculate_team_stats(
    db: Session, user_id: int, org_id: int,
    branch_user_ids: Optional[list] = None,
) -> dict:
    """Team workload, backlog, SLA missed counts."""
    try:
        today = date.today()
        team_members = db.query(User).filter(User.organization_id == org_id, User.is_active == True).all()
        has_team = len(team_members) > 1
        if not has_team:
            return dict(_DEFAULT_TEAM_STATS)

        team_member_ids = [u.id for u in team_members]
        workload_result = db.query(
            func.count(Loan.id).label('total'),
            func.count(func.distinct(Loan.loan_officer_id)).label('lo_count'),
        ).filter(
            Loan.organization_id == org_id,
            Loan.loan_officer_id.in_(team_member_ids),
            Loan.stage.notin_(TERMINAL_STAGES),
        ).first()

        total_active = workload_result.total or 0
        lo_count = workload_result.lo_count or 1
        avg_workload = round(total_active / lo_count, 1)

        backlog_filters = [Task.organization_id == org_id, Task.status == "pending", Task.due_date < today]
        if branch_user_ids is not None:
            backlog_filters.append(Task.owner_id.in_(branch_user_ids))
        backlog = db.query(func.count(Task.id)).filter(*backlog_filters).scalar() or 0

        sla_filters = [Loan.organization_id == org_id, Loan.sla_status == "behind", Loan.stage.notin_(TERMINAL_STAGES)]
        if branch_user_ids is not None:
            sla_filters.append(Loan.loan_officer_id.in_(branch_user_ids))
        sla_missed = db.query(func.count(Loan.id)).filter(*sla_filters).scalar() or 0

        insights = []
        if backlog > 5:
            insights.append(f"{backlog} overdue tasks need attention — consider redistributing workload.")
        if sla_missed > 0:
            insights.append(f"{sla_missed} loans are behind SLA targets. Review processing bottlenecks.")
        if avg_workload > 15:
            insights.append(f"Average workload is {avg_workload} files/person — capacity may be stretched.")
        if not insights:
            insights.append("Team is operating within normal parameters.")

        return {"has_team": True, "avg_workload": avg_workload, "backlog": backlog, "sla_missed": sla_missed, "insights": insights}
    except Exception as e:
        logger.error("calculate_team_stats failed: %s", e)
        db.rollback()
        return dict(_DEFAULT_TEAM_STATS)


# =============================================================================
# 7. Efficiency Summary
# =============================================================================

def calculate_efficiency_summary(
    db: Session, user_id: int, org_id: int,
    branch_user_ids: Optional[list] = None,
    lookback_days: int = 30,
) -> dict:
    """Overall efficiency score, pull-through rate, avg time to close, loans behind."""
    try:
        today = date.today()
        cutoff = today - timedelta(days=lookback_days)

        # Average time to close
        ttc_filters = [Loan.stage == LoanStage.FUNDED, Loan.funded_date >= cutoff, Loan.funded_date.isnot(None)]
        _apply_scope(ttc_filters, Loan.loan_officer_id, user_id, org_id, branch_user_ids, Loan.organization_id)
        avg_ttc = db.query(
            func.avg(func.extract('epoch', Loan.funded_date - func.coalesce(Loan.application_date, Loan.created_at)) / 86400)
        ).filter(*ttc_filters, func.coalesce(Loan.application_date, Loan.created_at).isnot(None)).scalar()
        avg_time_to_close = float(avg_ttc) if avg_ttc and avg_ttc > 0 else 0

        # Pull-through rate (90-day cohort)
        ninety_days_ago = today - timedelta(days=90)
        cohort_filters = [Loan.created_at <= ninety_days_ago]
        _apply_scope(cohort_filters, Loan.loan_officer_id, user_id, org_id, branch_user_ids, Loan.organization_id)
        cohort = db.query(
            func.count(Loan.id).label('total'),
            func.count(case((Loan.stage == LoanStage.FUNDED, 1))).label('funded'),
        ).filter(*cohort_filters).first()
        pull_through_rate = int(cohort.funded / cohort.total * 100) if (cohort.total or 0) > 0 else 0

        # Loans falling behind
        behind_filters = [Loan.stage.in_([LoanStage.PROCESSING, LoanStage.UW_RECEIVED]), Loan.days_in_stage > 14]
        _apply_scope(behind_filters, Loan.loan_officer_id, user_id, org_id, branch_user_ids, Loan.organization_id)
        loans_behind = db.query(func.count(Loan.id)).filter(*behind_filters).scalar() or 0

        # Automation rate
        task_filters = [Task.created_at >= cutoff]
        _apply_scope(task_filters, Task.owner_id, user_id, org_id, branch_user_ids, Task.organization_id)
        total_tasks = db.query(func.count(Task.id)).filter(*task_filters).scalar() or 1

        ai_filters = [AIColleagueAction.created_at >= cutoff]
        _apply_scope(ai_filters, AIColleagueAction.user_id, user_id, org_id, branch_user_ids, AIColleagueAction.organization_id)
        ai_count = db.query(func.count(AIColleagueAction.id)).filter(*ai_filters).scalar() or 0
        automation_rate = int(ai_count / (total_tasks + ai_count) * 100) if (total_tasks + ai_count) > 0 else 0

        # Overall score (weighted)
        time_score = (100 - min(avg_time_to_close, 100)) if avg_time_to_close > 0 else 50
        overall_score = int(
            pull_through_rate * 0.3 +
            time_score * 0.3 +
            (100 - min(loans_behind * 5, 100)) * 0.2 +
            automation_rate * 0.2
        )

        return {
            "overallScore": overall_score,
            "avgTimeToClose": round(avg_time_to_close, 1),
            "pullThroughRate": pull_through_rate,
            "loansFallingBehind": loans_behind,
            "automationRate": automation_rate,
        }
    except Exception as e:
        logger.error("calculate_efficiency_summary failed: %s", e)
        db.rollback()
        return dict(_DEFAULT_EFFICIENCY)


# =============================================================================
# 8-11. Extracted helpers (moved from dashboard_routes.py)
# =============================================================================

def calculate_stage_performance(
    db: Session, user_id: int, org_id: int,
    branch_user_ids: Optional[list] = None,
    lookback_days: int = 30,
) -> list:
    """Stage performance: efficiency scores and status per pipeline stage."""
    stage_configs = [
        {"name": "Lead Generation", "stages": [LeadStage.NEW], "type": "lead", "target_days": 2},
        {"name": "Pre-Qualification", "stages": [LeadStage.ATTEMPTED_CONTACT, LeadStage.PRE_QUALIFIED], "type": "lead", "target_days": 5},
        {"name": "Application", "stages": [LeadStage.APPLICATION], "type": "lead", "target_days": 7},
        {"name": "Processing", "stages": [LoanStage.PROCESSING], "type": "loan", "target_days": 10},
        {"name": "Underwriting", "stages": [LoanStage.SUBMITTED, LoanStage.UW_RECEIVED, LoanStage.UNDERWRITING], "type": "loan", "target_days": 7},
        {"name": "Clear to Close", "stages": [LoanStage.CTC], "type": "loan", "target_days": 3},
        {"name": "Closing", "stages": [LoanStage.DOCS_OUT, LoanStage.FUNDED], "type": "loan", "target_days": 5},
    ]
    try:
        now = datetime.now(timezone.utc)
        results = []
        for config in stage_configs:
            if config["type"] == "lead":
                qf = [Lead.stage.in_(config["stages"])]
                _apply_scope(qf, Lead.owner_id, user_id, org_id, branch_user_ids, Lead.organization_id)
                row = db.query(
                    func.count(Lead.id).label('cnt'),
                    func.avg(func.extract('epoch', now - func.coalesce(Lead.stage_changed_at, Lead.created_at)) / 86400).label('avg_days'),
                ).filter(*qf).first()
            else:
                qf = [Loan.stage.in_(config["stages"])]
                _apply_scope(qf, Loan.loan_officer_id, user_id, org_id, branch_user_ids, Loan.organization_id)
                row = db.query(
                    func.count(Loan.id).label('cnt'),
                    func.avg(func.coalesce(Loan.days_in_stage, func.extract('epoch', now - Loan.created_at) / 86400)).label('avg_days'),
                ).filter(*qf).first()

            count = row.cnt or 0
            avg_days = float(row.avg_days or 0) if count > 0 else 0
            efficiency = max(0, min(100, int(100 - max(0, (avg_days - config["target_days"]) * 10)))) if count > 0 else 100
            status = "on-track" if efficiency >= 80 else ("slightly-delayed" if efficiency >= 60 else "behind")
            results.append({"name": config["name"], "efficiency": efficiency, "status": status})
        return results
    except Exception as e:
        logger.error("calculate_stage_performance failed: %s", e)
        db.rollback()
        return []


def calculate_team_performance(
    db: Session, user_id: int, org_id: int,
    branch_user_ids: Optional[list] = None,
    lookback_days: int = 30,
) -> list:
    """Performance scores by role category (LOs, Processors, Underwriters, Closers)."""
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
        current_user = db.query(User).filter(User.id == user_id).first()
        if not current_user:
            return []

        results = []

        # LO performance
        lo_filters = [Lead.created_at >= cutoff]
        _apply_scope(lo_filters, Lead.owner_id, user_id, org_id, branch_user_ids, Lead.organization_id)
        lo_metrics = db.query(
            func.count(Lead.id).label('total_leads'),
            func.count(func.nullif(Lead.stage == LeadStage.CLOSED, False)).label('converted'),
        ).filter(*lo_filters).first()
        total = lo_metrics.total_leads or 0
        converted = lo_metrics.converted or 0
        lo_conv = (converted / total * 100) if total > 0 else 0
        results.append({"role": "Loan Officers", "performance": min(100, max(0, int(60 + lo_conv * 2)))})

        # Processor performance
        proc_filters = [Loan.stage == LoanStage.PROCESSING]
        _apply_scope(proc_filters, Loan.loan_officer_id, user_id, org_id, branch_user_ids, Loan.organization_id)
        proc = db.query(func.count(Loan.id).label('cnt'), func.avg(func.coalesce(Loan.days_in_stage, 0)).label('avg_days')).filter(*proc_filters).first()
        proc_perf = max(0, min(100, int(100 - max(0, (float(proc.avg_days or 0) - 10) * 5)))) if (proc.cnt or 0) > 0 else 85
        results.append({"role": "Processors", "performance": proc_perf})

        # UW performance
        uw_filters = [Loan.stage.in_([LoanStage.UW_RECEIVED, LoanStage.UNDERWRITING])]
        _apply_scope(uw_filters, Loan.loan_officer_id, user_id, org_id, branch_user_ids, Loan.organization_id)
        uw = db.query(func.count(Loan.id).label('cnt'), func.avg(func.coalesce(Loan.days_in_stage, 0)).label('avg_days')).filter(*uw_filters).first()
        uw_perf = max(0, min(100, int(100 - max(0, (float(uw.avg_days or 0) - 7) * 5)))) if (uw.cnt or 0) > 0 else 80
        results.append({"role": "Underwriters", "performance": uw_perf})

        # Closer performance
        close_filters = [Loan.stage == LoanStage.FUNDED, Loan.funded_date >= cutoff.date()]
        _apply_scope(close_filters, Loan.loan_officer_id, user_id, org_id, branch_user_ids, Loan.organization_id)
        funded = db.query(func.count(Loan.id)).filter(*close_filters).scalar() or 0
        results.append({"role": "Closers", "performance": min(100, max(0, 75 + funded * 2)) if funded > 0 else 85})

        return results
    except Exception as e:
        logger.error("calculate_team_performance failed: %s", e)
        db.rollback()
        return []


def calculate_bottlenecks(
    db: Session, user_id: int, org_id: int,
    branch_user_ids: Optional[list] = None,
) -> list:
    """Dynamic bottlenecks: processing delays, stuck leads, UW delays, rate locks, app delays."""
    try:
        now = datetime.now(timezone.utc)
        bottlenecks = []

        # 1. Processing delays
        pf = [Loan.stage == LoanStage.PROCESSING, Loan.days_in_stage > 10]
        _apply_scope(pf, Loan.loan_officer_id, user_id, org_id, branch_user_ids, Loan.organization_id)
        proc = db.query(func.count(Loan.id).label('cnt'), func.avg(func.coalesce(Loan.days_in_stage, 0)).label('avg_delay')).filter(*pf).first()
        if (proc.cnt or 0) > 0:
            bottlenecks.append({"issue": "Loans Delayed in Processing", "stage": "Processing", "affectedLoans": proc.cnt, "avgDelay": f"{round(float(proc.avg_delay or 0), 1)} days"})

        # 2. Stuck leads
        lf = [Lead.stage == LeadStage.NEW, Lead.created_at < now - timedelta(days=3)]
        _apply_scope(lf, Lead.owner_id, user_id, org_id, branch_user_ids, Lead.organization_id)
        stuck = db.query(func.count(Lead.id)).filter(*lf).scalar() or 0
        if stuck > 0:
            bottlenecks.append({"issue": "Leads Awaiting Initial Contact", "stage": "Lead Generation", "affectedLoans": stuck, "avgDelay": ">3 days"})

        # 3. UW delays
        uf = [Loan.stage.in_([LoanStage.UW_RECEIVED, LoanStage.UNDERWRITING]), Loan.days_in_stage > 7]
        _apply_scope(uf, Loan.loan_officer_id, user_id, org_id, branch_user_ids, Loan.organization_id)
        uw = db.query(func.count(Loan.id).label('cnt'), func.avg(func.coalesce(Loan.days_in_stage, 0)).label('avg_delay')).filter(*uf).first()
        if (uw.cnt or 0) > 0:
            bottlenecks.append({"issue": "Underwriting Taking Longer Than Expected", "stage": "Underwriting", "affectedLoans": uw.cnt, "avgDelay": f"{round(float(uw.avg_delay or 0), 1)} days"})

        # 4. Rate lock expiring
        rf = [Loan.lock_expiration_date.isnot(None), Loan.lock_expiration_date <= now + timedelta(days=7), Loan.stage.notin_([LoanStage.FUNDED, LoanStage.CANCELLED, LoanStage.DENIED])]
        _apply_scope(rf, Loan.loan_officer_id, user_id, org_id, branch_user_ids, Loan.organization_id)
        rate_lock = db.query(func.count(Loan.id)).filter(*rf).scalar() or 0
        if rate_lock > 0:
            bottlenecks.append({"issue": "Rate Lock Expiring Soon", "stage": "All Active Stages", "affectedLoans": rate_lock, "avgDelay": "<7 days to expiry"})

        # 5. Application delays
        af = [Lead.stage == LeadStage.APPLICATION, Lead.stage_changed_at < now - timedelta(days=14)]
        _apply_scope(af, Lead.owner_id, user_id, org_id, branch_user_ids, Lead.organization_id)
        app = db.query(func.count(Lead.id).label('cnt'), func.avg(func.extract('epoch', now - Lead.stage_changed_at) / 86400).label('avg_delay')).filter(*af).first()
        if (app.cnt or 0) > 0:
            bottlenecks.append({"issue": "Applications Pending Completion", "stage": "Application", "affectedLoans": app.cnt, "avgDelay": f"{round(float(app.avg_delay or 0), 1)} days"})

        return bottlenecks
    except Exception as e:
        logger.error("calculate_bottlenecks failed: %s", e)
        db.rollback()
        return []


def calculate_efficiency_trends(
    db: Session, user_id: int, org_id: int,
    branch_user_ids: Optional[list] = None,
    lookback_days: int = 30,
) -> dict:
    """Period-over-period trend values for efficiency metrics."""
    try:
        now = datetime.now(timezone.utc)
        current_start = now - timedelta(days=lookback_days)
        prev_start = now - timedelta(days=lookback_days * 2)

        def _funded_count(start_date, end_date=None):
            qf = [Loan.stage == LoanStage.FUNDED, Loan.funded_date >= start_date.date()]
            if end_date:
                qf.append(Loan.funded_date < end_date.date())
            _apply_scope(qf, Loan.loan_officer_id, user_id, org_id, branch_user_ids, Loan.organization_id)
            return db.query(func.count(Loan.id)).filter(*qf).scalar() or 0

        def _apps_count(start_date, end_date=None):
            qf = [Loan.created_at >= start_date]
            if end_date:
                qf.append(Loan.created_at < end_date)
            _apply_scope(qf, Loan.loan_officer_id, user_id, org_id, branch_user_ids, Loan.organization_id)
            return db.query(func.count(Loan.id)).filter(*qf).scalar() or 1

        current_funded = _funded_count(current_start)
        current_apps = _apps_count(current_start)
        current_pt = (current_funded / current_apps * 100) if current_apps > 0 else 0

        prev_funded = _funded_count(prev_start, current_start)
        prev_apps = _apps_count(prev_start, current_start)
        prev_pt = (prev_funded / prev_apps * 100) if prev_apps > 0 else 0

        def _avg_ttc(start_date, end_date=None):
            qf = [Loan.stage == LoanStage.FUNDED, Loan.funded_date >= start_date.date(), Loan.funded_date.isnot(None)]
            if end_date:
                qf.append(Loan.funded_date < end_date.date())
            _apply_scope(qf, Loan.loan_officer_id, user_id, org_id, branch_user_ids, Loan.organization_id)
            qf.append(func.coalesce(Loan.application_date, Loan.created_at).isnot(None))
            result = db.query(func.avg(func.extract('epoch', Loan.funded_date - func.coalesce(Loan.application_date, Loan.created_at)) / 86400)).filter(*qf).scalar()
            return float(result) if result and result > 0 else 0

        current_ttc = _avg_ttc(current_start)
        prev_ttc = _avg_ttc(prev_start, current_start)

        def calc_change(current, previous):
            if previous == 0:
                return 0 if current == 0 else 100
            return round(((current - previous) / previous) * 100, 1)

        pt_change = calc_change(current_pt, prev_pt)
        ttc_change = calc_change(prev_ttc, current_ttc) if current_ttc > 0 else 0
        overall = round((pt_change + ttc_change) / 2, 1)

        behind_filters = [Loan.stage.in_([LoanStage.PROCESSING, LoanStage.UW_RECEIVED]), Loan.days_in_stage > 14]
        _apply_scope(behind_filters, Loan.loan_officer_id, user_id, org_id, branch_user_ids, Loan.organization_id)
        behind = db.query(func.count(Loan.id)).filter(*behind_filters).scalar() or 0

        return {
            "overall_trend": overall,
            "pull_through_change": pt_change,
            "time_to_close_change": ttc_change,
            "loans_behind_change": -behind if behind > 0 else 0,
            "automation_change": 0,
        }
    except Exception as e:
        logger.error("calculate_efficiency_trends failed: %s", e)
        db.rollback()
        return {"overall_trend": 0, "pull_through_change": 0, "time_to_close_change": 0, "loans_behind_change": 0, "automation_change": 0}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/timothyloss/my-project/mortgage-crm/backend && python -m pytest tests/test_dashboard_metrics_service.py -v`
Expected: 3 PASS

- [ ] **Step 5: Add more tests for other key functions**

Append to `backend/tests/test_dashboard_metrics_service.py`:

```python
class TestCalculateBottlenecks:
    def test_returns_empty_list_on_error(self):
        from services.dashboard_metrics_service import calculate_bottlenecks
        db, query_mock = _make_mock_db()
        db.query.side_effect = Exception("DB error")
        result = calculate_bottlenecks(db, user_id=1, org_id=1, branch_user_ids=[1])
        assert result == []
        db.rollback.assert_called_once()


class TestCalculateEfficiencySummary:
    def test_returns_default_on_error(self):
        from services.dashboard_metrics_service import calculate_efficiency_summary
        db, query_mock = _make_mock_db()
        db.query.side_effect = Exception("DB error")
        result = calculate_efficiency_summary(db, user_id=1, org_id=1, branch_user_ids=[1])
        assert result["overallScore"] == 0
        assert result["pullThroughRate"] == 0
        db.rollback.assert_called_once()


class TestCalculateLoanIssues:
    def test_returns_empty_list_on_error(self):
        from services.dashboard_metrics_service import calculate_loan_issues
        db, query_mock = _make_mock_db()
        db.query.side_effect = Exception("DB error")
        result = calculate_loan_issues(db, user_id=1, org_id=1, branch_user_ids=[1])
        assert result == []
        db.rollback.assert_called_once()


class TestCalculateProfitability:
    def test_returns_default_on_error(self):
        from services.dashboard_metrics_service import calculate_profitability
        db, query_mock = _make_mock_db()
        db.query.side_effect = Exception("DB error")
        result = calculate_profitability(db, user_id=1, org_id=1, branch_user_ids=[1])
        assert result["funded_ytd"] == 0
        assert "Fund loans" in result["insights"][0]
        db.rollback.assert_called_once()
```

- [ ] **Step 6: Run full test suite**

Run: `cd /Users/timothyloss/my-project/mortgage-crm/backend && python -m pytest tests/test_dashboard_metrics_service.py -v`
Expected: 7 PASS

- [ ] **Step 7: Commit**

```bash
git add backend/services/dashboard_metrics_service.py backend/tests/test_dashboard_metrics_service.py
git commit -m "feat: shared dashboard metrics service with 11 query functions"
```

---

### Task 2: Refactor dashboard_routes.py to use shared service

**Files:**
- Modify: `backend/routes/dashboard_routes.py`

- [ ] **Step 1: Replace the 4 top-level helper functions with imports**

At the top of `backend/routes/dashboard_routes.py`, replace lines 40-519 (the 4 helper function definitions) with:

```python
# =============================================================================
# SHARED METRICS (extracted to services/dashboard_metrics_service.py)
# =============================================================================
from services.dashboard_metrics_service import (
    calculate_stage_performance,
    calculate_team_performance,
    calculate_bottlenecks,
    calculate_efficiency_trends,
    calculate_production_metrics,
    calculate_pipeline_stats,
    calculate_lead_metrics,
    calculate_profitability,
    calculate_loan_issues,
    calculate_team_stats,
    calculate_efficiency_summary,
)
```

- [ ] **Step 2: Replace inline production metrics section (lines ~640-692) with shared service call**

Replace the production metrics block with:

```python
    user_metadata = current_user.user_metadata or {}
    production = calculate_production_metrics(
        db, current_user.id, org_id,
        branch_user_ids=branch_user_ids,
        user_metadata=user_metadata,
    )
```

- [ ] **Step 3: Replace inline pipeline stats section (lines ~694-868) with shared service call**

Replace the pipeline stats block with:

```python
    pipeline_stats = calculate_pipeline_stats(db, current_user.id, org_id, branch_user_ids=branch_user_ids)
    total_loan_count_from_pipeline = sum(s.get("count", 0) for s in pipeline_stats if s["id"] not in ("new", "preapproved", "funded"))
```

- [ ] **Step 4: Replace inline lead metrics section (lines ~899-989) with shared service call**

Replace with:

```python
    lead_metrics = calculate_lead_metrics(db, current_user.id, org_id, branch_user_ids=branch_user_ids)
```

- [ ] **Step 5: Replace inline team stats section (lines ~1036-1096) with shared service call**

Replace with:

```python
    team_stats = calculate_team_stats(db, current_user.id, org_id, branch_user_ids=branch_user_ids)
```

- [ ] **Step 6: Replace inline loan issues section (lines ~1223-1255) with shared service call**

Replace with:

```python
    loan_issues = calculate_loan_issues(db, current_user.id, org_id, branch_user_ids=branch_user_ids)
```

- [ ] **Step 7: Replace inline profitability section (lines ~1257-1323) with shared service call**

Replace with:

```python
    profitability = calculate_profitability(db, current_user.id, org_id, branch_user_ids=branch_user_ids)
```

- [ ] **Step 8: Replace inline efficiency metrics section (lines ~1325-1458) with shared service call**

Replace the avg_time_to_close + pull-through + loans_behind + automation rate + overall score blocks with:

```python
    eff_summary = calculate_efficiency_summary(db, current_user.id, org_id, branch_user_ids=branch_user_ids)
    total_loan_count = total_loan_count_from_pipeline
```

Then update the efficiency dict assembly to use `eff_summary`:

```python
    try:
        trends = calculate_efficiency_trends(db, current_user.id, org_id, branch_user_ids=branch_user_ids)
    except Exception as e:
        logger.error("Error in get_dashboard (efficiency_trends): %s", e)
        trends = {"overall_trend": 0, "time_to_close_change": 0, "pull_through_change": 0, "loans_behind_change": 0, "automation_change": 0}

    try:
        stage_perf = calculate_stage_performance(db, current_user.id, org_id, branch_user_ids=branch_user_ids) if total_loan_count > 0 else []
    except Exception as e:
        logger.error("Error in get_dashboard (stage_performance): %s", e)
        stage_perf = []

    try:
        team_perf = calculate_team_performance(db, current_user.id, org_id, branch_user_ids=branch_user_ids) if total_loan_count > 0 else []
    except Exception as e:
        logger.error("Error in get_dashboard (team_performance): %s", e)
        team_perf = []

    try:
        bottleneck_list = calculate_bottlenecks(db, current_user.id, org_id, branch_user_ids=branch_user_ids)
    except Exception as e:
        logger.error("Error in get_dashboard (bottlenecks): %s", e)
        bottleneck_list = []

    efficiency = {
        "overallScore": eff_summary["overallScore"],
        "trend": trends["overall_trend"],
        "avgTimeToClose": eff_summary["avgTimeToClose"],
        "avgTimeToCloseChange": trends["time_to_close_change"],
        "pullThroughRate": eff_summary["pullThroughRate"],
        "pullThroughRateChange": trends["pull_through_change"],
        "loansFallingBehind": eff_summary["loansFallingBehind"],
        "loansFallingBehindChange": trends["loans_behind_change"],
        "automationRate": eff_summary["automationRate"],
        "automationRateChange": trends["automation_change"],
        "customerSatisfaction": None,
        "customerSatisfactionChange": 0,
        "stages": stage_perf,
        "team": team_perf,
        "bottleneckCount": len(bottleneck_list),
        "bottlenecks": bottleneck_list,
    }
```

- [ ] **Step 9: Verify the route still works — import check**

Run: `cd /Users/timothyloss/my-project/mortgage-crm/backend && python -c "from routes.dashboard_routes import router; print('OK')" `
Expected: `OK`

- [ ] **Step 10: Commit**

```bash
git add backend/routes/dashboard_routes.py
git commit -m "refactor: dashboard route uses shared metrics service"
```

---

### Task 3: Integrate dashboard snapshot into morning briefing service

**Files:**
- Modify: `backend/services/morning_briefing_service.py`

- [ ] **Step 1: Write failing test for `_query_dashboard_snapshot()`**

Append to `backend/tests/test_morning_briefing_service.py`:

```python
class TestDashboardSnapshot:
    """Test _query_dashboard_snapshot integration."""

    def test_individual_level_returns_snapshot(self):
        Svc = _real_service()
        svc = Svc()
        db = MagicMock()
        # Mock all shared service functions to return defaults
        with patch("services.morning_briefing_service.dms") as mock_dms:
            mock_dms.calculate_production_metrics.return_value = {"monthlyActual": 5}
            mock_dms.calculate_pipeline_stats.return_value = []
            mock_dms.calculate_lead_metrics.return_value = {"new_today": 0}
            mock_dms.calculate_efficiency_summary.return_value = {"overallScore": 50}
            mock_dms.calculate_profitability.return_value = {"funded_ytd": 0}
            mock_dms.calculate_loan_issues.return_value = []
            mock_dms.calculate_bottlenecks.return_value = []
            mock_dms.calculate_stage_performance.return_value = []
            result = svc._query_dashboard_snapshot(db, user_id=1, org_id=1, level="individual")
        assert "production" in result
        assert "efficiency" in result
        assert "team_stats" not in result  # individual level

    def test_manager_level_includes_team_stats(self):
        Svc = _real_service()
        svc = Svc()
        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = []  # no direct reports
        with patch("services.morning_briefing_service.dms") as mock_dms:
            mock_dms.calculate_production_metrics.return_value = {}
            mock_dms.calculate_pipeline_stats.return_value = []
            mock_dms.calculate_lead_metrics.return_value = {}
            mock_dms.calculate_efficiency_summary.return_value = {}
            mock_dms.calculate_profitability.return_value = {}
            mock_dms.calculate_loan_issues.return_value = []
            mock_dms.calculate_bottlenecks.return_value = []
            mock_dms.calculate_stage_performance.return_value = []
            mock_dms.calculate_team_stats.return_value = {"has_team": True}
            mock_dms.calculate_team_performance.return_value = []
            result = svc._query_dashboard_snapshot(db, user_id=1, org_id=1, level="manager")
        assert "team_stats" in result
        assert "team_performance" in result
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/timothyloss/my-project/mortgage-crm/backend && python -m pytest tests/test_morning_briefing_service.py::TestDashboardSnapshot -v`
Expected: FAIL — `AttributeError: 'MorningBriefingService' object has no attribute '_query_dashboard_snapshot'`

- [ ] **Step 3: Add `dashboard_snapshot` field to BriefingContext**

In `backend/services/morning_briefing_service.py`, add to the `BriefingContext` dataclass (after line 109):

```python
    # Dashboard snapshot (all levels)
    dashboard_snapshot: Optional[Dict[str, Any]] = None
```

- [ ] **Step 4: Add import for shared service**

At the top of `backend/services/morning_briefing_service.py`, after the existing imports (around line 15), add:

```python
import services.dashboard_metrics_service as dms
```

- [ ] **Step 5: Add `_query_dashboard_snapshot()` method**

In the `MorningBriefingService` class, after `_query_yesterday_activity()` (around line 425), add:

```python
    def _query_dashboard_snapshot(
        self, db: Session, user_id: int, org_id: int, level: str,
        user_metadata: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Gather full dashboard snapshot scoped by briefing level."""
        if level == "individual":
            branch_user_ids = [user_id]
        elif level == "manager":
            report_rows = db.query(User.id).filter(
                User.manager_id == user_id, User.is_active == True, User.organization_id == org_id
            ).all()
            branch_user_ids = [user_id] + [r[0] for r in report_rows]
        else:
            branch_user_ids = None

        snapshot = {
            "production": dms.calculate_production_metrics(db, user_id, org_id, branch_user_ids, user_metadata),
            "pipeline_stats": dms.calculate_pipeline_stats(db, user_id, org_id, branch_user_ids),
            "lead_metrics": dms.calculate_lead_metrics(db, user_id, org_id, branch_user_ids),
            "efficiency": dms.calculate_efficiency_summary(db, user_id, org_id, branch_user_ids),
            "profitability": dms.calculate_profitability(db, user_id, org_id, branch_user_ids),
            "loan_issues": dms.calculate_loan_issues(db, user_id, org_id, branch_user_ids),
            "bottlenecks": dms.calculate_bottlenecks(db, user_id, org_id, branch_user_ids),
            "stage_performance": dms.calculate_stage_performance(db, user_id, org_id, branch_user_ids),
        }

        if level in ("manager", "leadership"):
            snapshot["team_stats"] = dms.calculate_team_stats(db, user_id, org_id, branch_user_ids)
            snapshot["team_performance"] = dms.calculate_team_performance(db, user_id, org_id, branch_user_ids)

        return snapshot
```

Note: The `User` import is needed — add `from database.models import User` at the top if not already imported.

- [ ] **Step 6: Integrate into `build_context()`**

In `build_context()` (around line 750, after the leadership roll-up), add:

```python
        # Dashboard snapshot (all levels)
        user_metadata = getattr(user, "user_metadata", None) or {}
        ctx.dashboard_snapshot = self._query_dashboard_snapshot(db, user_id, org_id, level, user_metadata)
```

- [ ] **Step 7: Add dashboard data to AI narrative prompt**

In `_format_context_for_ai()` (around line 933, before the final `return`), add:

```python
        # Dashboard snapshot
        ds = ctx.dashboard_snapshot
        if ds:
            lines.append("")
            lines.append("DASHBOARD SNAPSHOT:")
            prod = ds.get("production", {})
            if prod:
                lines.append(f"  Production: {prod.get('monthlyActual', 0)}/{prod.get('monthlyGoal', 0)} funded this month ({prod.get('monthlyProgress', 0)}%)")
            eff = ds.get("efficiency", {})
            if eff:
                lines.append(f"  Efficiency score: {eff.get('overallScore', 0)}/100")
                lines.append(f"  Pull-through rate: {eff.get('pullThroughRate', 0)}%")
                lines.append(f"  Avg time to close: {eff.get('avgTimeToClose', 0)} days")
                lines.append(f"  Loans falling behind: {eff.get('loansFallingBehind', 0)}")
            bn = ds.get("bottlenecks", [])
            if bn:
                lines.append(f"  Bottlenecks: {len(bn)} active")
            prof = ds.get("profitability", {})
            if prof and prof.get("funded_ytd", 0) > 0:
                lines.append(f"  Profitability: {prof['funded_ytd']} funded YTD, ${prof.get('total_volume', 0):,.0f} volume")
```

- [ ] **Step 8: Run tests**

Run: `cd /Users/timothyloss/my-project/mortgage-crm/backend && python -m pytest tests/test_morning_briefing_service.py -v`
Expected: All tests PASS

- [ ] **Step 9: Commit**

```bash
git add backend/services/morning_briefing_service.py backend/tests/test_morning_briefing_service.py
git commit -m "feat: dashboard snapshot in morning briefing service"
```

---

### Task 4: Add deep-linked dashboard section to briefing email template

**Files:**
- Modify: `backend/templates/morning_briefing_email.py`

- [ ] **Step 1: Add `_section_dashboard_snapshot()` helper function**

In `backend/templates/morning_briefing_email.py`, after `_section_conditions()` (around line 228), add:

```python
def _section_dashboard_snapshot(
    snapshot: Dict[str, Any],
    briefing_date: date,
    level: str,
    app_url: str = "https://app.perenniaai.com",
    brand_color: str = "#218d8d",
) -> str:
    """Render dashboard snapshot section with deep links to app."""
    if not snapshot:
        return ""

    date_str = briefing_date.isoformat()
    dash_link = f"{app_url}/dashboard?date={_esc(date_str)}"

    sections = []

    # Production
    prod = snapshot.get("production", {})
    if prod:
        monthly = prod.get("monthlyActual", 0)
        goal = prod.get("monthlyGoal", 0)
        progress = prod.get("monthlyProgress", 0)
        bar_width = min(progress, 100)
        sections.append(f"""
<h3 style="margin:16px 0 8px;font-size:13px;font-weight:700;color:#4a4a5a;text-transform:uppercase;">
  <a href="{dash_link}" style="color:{brand_color};text-decoration:none;">Production</a>
</h3>
<p style="margin:0 0 6px;font-size:14px;color:#1a1a2a;">{_esc(monthly)} / {_esc(goal)} funded this month ({_esc(progress)}%)</p>
<div style="background:#e8e8ed;border-radius:4px;height:8px;overflow:hidden;">
  <div style="background:{brand_color};height:100%;width:{bar_width}%;border-radius:4px;"></div>
</div>""")

    # Pipeline
    pipeline = snapshot.get("pipeline_stats", [])
    if pipeline:
        rows = ""
        for s in pipeline:
            if s.get("count", 0) > 0:
                stage_link = f'{app_url}/pipeline?stage={_esc(s["id"])}' if s.get("id") not in ("new", "preapproved") else f"{app_url}/leads"
                vol = f' &middot; ${s["volume"]:,.0f}' if s.get("volume") else ""
                alert = f' <span style="color:#e74c3c;font-weight:600;">({s["alerts"]} {s["alert_text"]})</span>' if s.get("alerts", 0) > 0 else ""
                rows += f'<tr><td style="padding:4px 8px;font-size:13px;border-bottom:1px solid #f0f0f4;"><a href="{stage_link}" style="color:{brand_color};text-decoration:none;">{_esc(s["name"])}</a></td><td style="padding:4px 8px;font-size:13px;border-bottom:1px solid #f0f0f4;text-align:right;font-weight:600;">{_esc(s["count"])}{vol}{alert}</td></tr>\n'
        if rows:
            sections.append(f"""
<h3 style="margin:16px 0 8px;font-size:13px;font-weight:700;color:#4a4a5a;text-transform:uppercase;">Pipeline</h3>
<table width="100%" cellpadding="0" cellspacing="0" style="background:#fafafa;border-radius:6px;overflow:hidden;">{rows}</table>""")

    # Efficiency
    eff = snapshot.get("efficiency", {})
    if eff:
        score = eff.get("overallScore", 0)
        score_color = "#27ae60" if score >= 70 else ("#f39c12" if score >= 40 else "#e74c3c")
        sections.append(f"""
<h3 style="margin:16px 0 8px;font-size:13px;font-weight:700;color:#4a4a5a;text-transform:uppercase;">
  <a href="{dash_link}" style="color:{brand_color};text-decoration:none;">Efficiency</a>
</h3>
<table width="100%" cellpadding="0" cellspacing="0">
<tr>
  <td style="font-size:28px;font-weight:700;color:{score_color};width:60px;">{_esc(score)}</td>
  <td style="font-size:13px;color:#4a4a5a;padding-left:12px;">
    Pull-through: {_esc(eff.get('pullThroughRate', 0))}% &middot;
    Avg close: {_esc(eff.get('avgTimeToClose', 0))}d &middot;
    Behind: {_esc(eff.get('loansFallingBehind', 0))}
  </td>
</tr>
</table>""")

    # Profitability
    prof = snapshot.get("profitability", {})
    if prof and prof.get("funded_ytd", 0) > 0:
        sections.append(f"""
<h3 style="margin:16px 0 8px;font-size:13px;font-weight:700;color:#4a4a5a;text-transform:uppercase;">
  <a href="{dash_link}" style="color:{brand_color};text-decoration:none;">Profitability</a>
</h3>
<p style="margin:0;font-size:13px;color:#4a4a5a;">
  {_esc(prof.get('funded_ytd', 0))} funded YTD &middot;
  ${prof.get('total_volume', 0):,.0f} volume &middot;
  Avg size ${prof.get('avg_loan_size', 0):,.0f} &middot;
  {_esc(prof.get('gain_on_sale_display', '--'))} gain
</p>""")

    # Loan issues
    issues = snapshot.get("loan_issues", [])
    if issues:
        rows = ""
        for issue in issues[:5]:
            loan_link = f'{app_url}/loans/{_esc(issue["id"])}'
            rows += f'<li style="margin:3px 0;font-size:13px;color:#4a4a5a;"><a href="{loan_link}" style="color:{brand_color};text-decoration:none;">{_esc(issue["borrower_name"])}</a> — {_esc(issue["issue"])}</li>\n'
        sections.append(f"""
<h3 style="margin:16px 0 8px;font-size:13px;font-weight:700;color:#e74c3c;text-transform:uppercase;">Loan Issues ({len(issues)})</h3>
<ul style="margin:0;padding-left:20px;">{rows}</ul>""")

    # Bottlenecks
    bns = snapshot.get("bottlenecks", [])
    if bns:
        rows = ""
        for bn in bns:
            stage_link = f'{app_url}/pipeline?stage={_esc(bn.get("stage", ""))}'
            rows += f'<li style="margin:3px 0;font-size:13px;color:#4a4a5a;"><a href="{stage_link}" style="color:{brand_color};text-decoration:none;">{_esc(bn["issue"])}</a> — {_esc(bn["affectedLoans"])} affected, {_esc(bn["avgDelay"])}</li>\n'
        sections.append(f"""
<h3 style="margin:16px 0 8px;font-size:13px;font-weight:700;color:#f39c12;text-transform:uppercase;">Bottlenecks ({len(bns)})</h3>
<ul style="margin:0;padding-left:20px;">{rows}</ul>""")

    # Team stats (manager/leadership only)
    ts = snapshot.get("team_stats")
    if ts and ts.get("has_team"):
        team_link = f"{app_url}/team"
        sections.append(f"""
<h3 style="margin:16px 0 8px;font-size:13px;font-weight:700;color:#4a4a5a;text-transform:uppercase;">
  <a href="{team_link}" style="color:{brand_color};text-decoration:none;">Team Stats</a>
</h3>
<p style="margin:0;font-size:13px;color:#4a4a5a;">
  Avg workload: {_esc(ts.get('avg_workload', 0))} &middot;
  Backlog: {_esc(ts.get('backlog', 0))} &middot;
  SLA missed: {_esc(ts.get('sla_missed', 0))}
</p>""")

    if not sections:
        return ""

    return f"""
<h2 style="margin:20px 0 4px;color:{brand_color};font-size:15px;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;">&#128202; Dashboard Snapshot</h2>
{"".join(sections)}"""
```

- [ ] **Step 2: Wire the new section into `render_briefing_email()`**

In `render_briefing_email()`, add `dashboard_snapshot` parameter after `team`:

```python
    dashboard_snapshot: Optional[Dict[str, Any]] = None,
```

Then, after the AI narrative sections and before the personal pipeline section (around line 76), add:

```python
    # Dashboard snapshot (always included when present)
    if dashboard_snapshot:
        sections.append(_section_dashboard_snapshot(
            dashboard_snapshot, briefing_date, level,
            app_url=app_url, brand_color=brand,
        ))
        sections.append(_divider())
```

- [ ] **Step 3: Verify import check**

Run: `cd /Users/timothyloss/my-project/mortgage-crm/backend && python -c "from templates.morning_briefing_email import render_briefing_email; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add backend/templates/morning_briefing_email.py
git commit -m "feat: dashboard snapshot section in briefing email with deep links"
```

---

### Task 5: Update email dispatch to pass dashboard_snapshot

**Files:**
- Modify: `backend/tasks/morning_briefing_tasks.py`

- [ ] **Step 1: Find where `render_briefing_email` is called and add `dashboard_snapshot` parameter**

In `backend/tasks/morning_briefing_tasks.py`, in the `generate_user_briefing()` function where `render_briefing_email()` is called, add the `dashboard_snapshot` kwarg:

```python
    dashboard_snapshot=briefing_data.get("dashboard_snapshot"),
```

The `briefing_data` dict is already loaded from `MorningBriefing.briefing_data` JSONB. Since `build_context()` now writes `dashboard_snapshot` into the context (and the task persists it into `briefing_data`), this just passes it through.

- [ ] **Step 2: Verify import check**

Run: `cd /Users/timothyloss/my-project/mortgage-crm/backend && python -c "from tasks.morning_briefing_tasks import dispatch_morning_briefings; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/tasks/morning_briefing_tasks.py
git commit -m "feat: pass dashboard_snapshot to briefing email template"
```

---

### Task 6: Add DashboardSnapshotSection frontend component

**Files:**
- Modify: `frontend/src/components/briefing/shared.js`

- [ ] **Step 1: Add `DashboardSnapshotSection` component**

At the end of `frontend/src/components/briefing/shared.js`, add:

```jsx
export function DashboardSnapshotSection({ snapshot, maxIssues }) {
  if (!snapshot) return null;

  const { production, pipeline_stats, efficiency, profitability, loan_issues, bottlenecks, team_stats, stage_performance } = snapshot;

  return (
    <div className="section-content dashboard-snapshot">
      {/* Production */}
      {production && (
        <div className="snapshot-subsection">
          <h5 className="snapshot-label">Production</h5>
          <div className="production-gauge">
            <div className="gauge-main">
              <span className="gauge-value">{production.monthlyActual || 0}</span>
              <span className="gauge-separator">/</span>
              <span className="gauge-goal">{production.monthlyGoal || 0}</span>
              <span className="gauge-label">this month</span>
            </div>
            <div className="gauge-bar">
              <div className="gauge-fill" style={{ width: `${Math.min(production.monthlyProgress || 0, 100)}%` }} />
            </div>
            <div className="gauge-secondary">
              <span>Daily: {production.dailyActual || 0}/{production.dailyGoal || 0}</span>
              <span>Weekly: {production.weeklyActual || 0}/{production.weeklyGoal || 0}</span>
              <span>Annual: {production.annualActual || 0}/{production.annualGoal || 0}</span>
            </div>
          </div>
        </div>
      )}

      {/* Pipeline */}
      {pipeline_stats && pipeline_stats.length > 0 && (
        <div className="snapshot-subsection">
          <h5 className="snapshot-label">Pipeline</h5>
          <div className="pipeline-compact">
            {pipeline_stats.filter(s => s.count > 0).map(s => (
              <div key={s.id} className="pipeline-item">
                <span className="pipeline-name">{s.name}</span>
                <span className="pipeline-count">{s.count}</span>
                {s.volume ? <span className="pipeline-vol">{formatVolume(s.volume)}</span> : null}
                {s.alerts > 0 && <span className="pipeline-alert">{s.alerts} {s.alert_text}</span>}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Efficiency */}
      {efficiency && (
        <div className="snapshot-subsection">
          <h5 className="snapshot-label">Efficiency</h5>
          <div className="metric-row">
            <div className="metric-item metric-score">
              <span className={`metric-value score-${efficiency.overallScore >= 70 ? 'good' : efficiency.overallScore >= 40 ? 'warn' : 'bad'}`}>
                {efficiency.overallScore}
              </span>
              <span className="metric-label">Score</span>
            </div>
            <div className="metric-item">
              <span className="metric-value">{efficiency.pullThroughRate}%</span>
              <span className="metric-label">Pull-Through</span>
            </div>
            <div className="metric-item">
              <span className="metric-value">{efficiency.avgTimeToClose}d</span>
              <span className="metric-label">Avg Close</span>
            </div>
            <div className="metric-item">
              <span className="metric-value">{efficiency.loansFallingBehind}</span>
              <span className="metric-label">Behind</span>
            </div>
          </div>
        </div>
      )}

      {/* Profitability */}
      {profitability && profitability.funded_ytd > 0 && (
        <div className="snapshot-subsection">
          <h5 className="snapshot-label">Profitability</h5>
          <div className="metric-row">
            <div className="metric-item">
              <span className="metric-value">{profitability.funded_ytd}</span>
              <span className="metric-label">Funded YTD</span>
            </div>
            <div className="metric-item">
              <span className="metric-value">{formatVolume(profitability.total_volume)}</span>
              <span className="metric-label">Volume</span>
            </div>
            <div className="metric-item">
              <span className="metric-value">{formatVolume(profitability.avg_loan_size)}</span>
              <span className="metric-label">Avg Size</span>
            </div>
            <div className="metric-item">
              <span className="metric-value">{profitability.gain_on_sale_display}</span>
              <span className="metric-label">Gain on Sale</span>
            </div>
          </div>
        </div>
      )}

      {/* Loan Issues */}
      {loan_issues && loan_issues.length > 0 && (
        <div className="snapshot-subsection">
          <h5 className="snapshot-label">Loan Issues ({loan_issues.length})</h5>
          <ul className="briefing-list">
            {loan_issues.slice(0, maxIssues || 10).map(issue => (
              <li key={issue.id}>
                <a href={`/loans/${issue.id}`} className="item-link"><strong>{issue.borrower_name}</strong></a>
                <span className="item-detail">{issue.issue}</span>
                <span className="item-badge warn">{issue.days_in_stage}d</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Bottlenecks */}
      {bottlenecks && bottlenecks.length > 0 && (
        <div className="snapshot-subsection">
          <h5 className="snapshot-label">Bottlenecks ({bottlenecks.length})</h5>
          <ul className="briefing-list">
            {bottlenecks.map((bn, i) => (
              <li key={i}>
                <span className="item-text">{bn.issue}</span>
                <span className="item-detail">{bn.affectedLoans} affected · {bn.avgDelay}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Team stats (manager/leadership) */}
      {team_stats && team_stats.has_team && (
        <div className="snapshot-subsection">
          <h5 className="snapshot-label">Team</h5>
          <div className="metric-row">
            <div className="metric-item">
              <span className="metric-value">{team_stats.avg_workload}</span>
              <span className="metric-label">Avg Workload</span>
            </div>
            <div className="metric-item">
              <span className="metric-value">{team_stats.backlog}</span>
              <span className="metric-label">Backlog</span>
            </div>
            <div className="metric-item">
              <span className="metric-value">{team_stats.sla_missed}</span>
              <span className="metric-label">SLA Missed</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/briefing/shared.js
git commit -m "feat: DashboardSnapshotSection component for briefing views"
```

---

### Task 7: Integrate DashboardSnapshotSection into BriefingPage and MorningBriefingCard

**Files:**
- Modify: `frontend/src/pages/BriefingPage.js`
- Modify: `frontend/src/components/dashboard/MorningBriefingCard.js`

- [ ] **Step 1: Add to BriefingPage.js imports**

In `frontend/src/pages/BriefingPage.js`, add `DashboardSnapshotSection` to the import from `shared`:

```javascript
import {
  healthLabel,
  formatVolume,
  SectionHeader,
  PipelineSection,
  AtRiskSection,
  ConditionsSection,
  StaleLeadsSection,
  AppointmentsSection,
  YesterdaySection,
  TeamSection,
  DashboardSnapshotSection,
} from '../components/briefing/shared';
```

- [ ] **Step 2: Destructure `dashboard_snapshot` in TodayTab**

In the destructured briefing fields (around line 124), add `dashboard_snapshot`:

```javascript
  const {
    ai_narrative, pipeline, at_risk, stale_leads,
    appointments, conditions, yesterday, team,
    briefing_level, briefing_date, dashboard_snapshot,
  } = briefing;
```

- [ ] **Step 3: Render DashboardSnapshotSection in TodayTab after narrative**

After the narrative div (around line 153) and before the Pipeline section, add:

```jsx
      {dashboard_snapshot && (
        <div className="briefing-section">
          <SectionHeader
            title="Dashboard Snapshot"
            icon=""
            isOpen={openSections.dashboard}
            onToggle={() => toggleSection('dashboard')}
          />
          {openSections.dashboard && <DashboardSnapshotSection snapshot={dashboard_snapshot} maxIssues={10} />}
        </div>
      )}
```

Also add `dashboard: true` to the `openSections` initial state:

```javascript
  const [openSections, setOpenSections] = useState({
    dashboard: true,
    pipeline: true,
    at_risk: true,
    conditions: true,
    stale_leads: true,
    appointments: true,
    yesterday: true,
    team: true,
  });
```

- [ ] **Step 4: Add to MorningBriefingCard.js imports**

In `frontend/src/components/dashboard/MorningBriefingCard.js`, add `DashboardSnapshotSection` to the import:

```javascript
import {
  healthLabel,
  SectionHeader,
  PipelineSection,
  AtRiskSection,
  ConditionsSection,
  StaleLeadsSection,
  AppointmentsSection,
  YesterdaySection,
  TeamSection,
  DashboardSnapshotSection,
} from '../briefing/shared';
```

- [ ] **Step 5: Destructure `dashboard_snapshot` in MorningBriefingCard**

In the destructured briefing fields (around line 147), add `dashboard_snapshot`:

```javascript
  const {
    ai_narrative,
    pipeline,
    at_risk,
    stale_leads,
    appointments,
    conditions,
    yesterday,
    team,
    briefing_level,
    briefing_date,
    dashboard_snapshot,
  } = briefing;
```

- [ ] **Step 6: Render DashboardSnapshotSection in card body after narrative**

After the narrative div (around line 214) and before the Pipeline section, add:

```jsx
          {/* Dashboard Snapshot */}
          {dashboard_snapshot && (
            <div className="briefing-section">
              <SectionHeader
                title="Dashboard Snapshot"
                icon="&#x1F4CA;"
                isOpen={openSections.dashboard}
                onToggle={() => toggleSection('dashboard')}
              />
              {openSections.dashboard && <DashboardSnapshotSection snapshot={dashboard_snapshot} maxIssues={5} />}
            </div>
          )}
```

Also add `dashboard: true` to the `openSections` initial state (line 55):

```javascript
  const [openSections, setOpenSections] = useState({
    dashboard: true,
    pipeline: true,
    at_risk: true,
    conditions: true,
    stale_leads: false,
    appointments: true,
    yesterday: false,
    team: false,
  });
```

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/BriefingPage.js frontend/src/components/dashboard/MorningBriefingCard.js
git commit -m "feat: render dashboard snapshot in briefing page and card"
```

---

### Task 8: Run full test suite and verify

**Files:** None (verification only)

- [ ] **Step 1: Run all backend briefing tests**

Run: `cd /Users/timothyloss/my-project/mortgage-crm/backend && python -m pytest tests/test_dashboard_metrics_service.py tests/test_morning_briefing_service.py tests/test_briefing_thread_models.py tests/test_briefing_routes.py -v`
Expected: All PASS

- [ ] **Step 2: Verify dashboard route still imports cleanly**

Run: `cd /Users/timothyloss/my-project/mortgage-crm/backend && python -c "from routes.dashboard_routes import router; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Verify briefing service imports cleanly**

Run: `cd /Users/timothyloss/my-project/mortgage-crm/backend && python -c "from services.morning_briefing_service import MorningBriefingService; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Start frontend dev server and verify no build errors**

Run: `cd /Users/timothyloss/my-project/mortgage-crm/frontend && npx vite build --mode development 2>&1 | tail -5`
Expected: Build succeeds without errors

- [ ] **Step 5: Final commit if any fixups needed**

```bash
git add -A && git commit -m "fix: post-integration cleanup"
```
