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
from database.models import User, Lead, Loan, Task, AIColleagueAction, MUMClient

logger = logging.getLogger(__name__)

TERMINAL_STAGES = [
    LoanStage.FUNDED, LoanStage.CANCELLED, LoanStage.DENIED,
    LoanStage.DEAD, LoanStage.WITHDRAWN, LoanStage.DOES_NOT_QUALIFY,
    LoanStage.NURTURE,
]

_DEFAULT_PRODUCTION = {
    "annualGoal": 0, "annualActual": 0, "annualProgress": 0,
    "monthlyGoal": 0, "monthlyActual": 0, "monthlyProgress": 0,
    "weeklyGoal": 0, "weeklyActual": 0, "weeklyProgress": 0,
    "dailyGoal": 0, "dailyActual": 0, "dailyProgress": 0,
}

_DEFAULT_LEAD_METRICS = {
    "new_today": 0, "avg_contact_time": 0, "conversion_rate": 0,
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
    "gain_on_sale": 0, "gain_on_sale_display": None,
    "revenue_per_loan": 0, "revenue_per_loan_display": None,
    "avg_points": 0, "cost_per_loan": None, "net_margin": None,
    "insights": [],
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
        annual_goal = goals.get('annualGoal', 0)
        monthly_goal = goals.get('monthlyGoal', 0)
        weekly_goal = goals.get('weeklyGoal', 0)
        daily_goal = goals.get('dailyGoal', 0)

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
        avg_contact_time = round(float(avg_contact), 1) if avg_contact else 0

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
            "gain_on_sale_display": f"{gain_bps} bps" if gain_bps > 0 else None,
            "revenue_per_loan": round(avg_orig, 2) if avg_orig > 0 else 0,
            "revenue_per_loan_display": f"${avg_orig:,.0f}" if avg_orig > 0 else None,
            "avg_points": round(avg_points, 3),
            "cost_per_loan": None,
            "net_margin": f"{gain_bps} bps" if gain_bps > 0 else None,
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
        proc_perf = max(0, min(100, int(100 - max(0, (float(proc.avg_days or 0) - 10) * 5)))) if (proc.cnt or 0) > 0 else 0
        results.append({"role": "Processors", "performance": proc_perf})

        # UW performance
        uw_filters = [Loan.stage.in_([LoanStage.UW_RECEIVED, LoanStage.UNDERWRITING])]
        _apply_scope(uw_filters, Loan.loan_officer_id, user_id, org_id, branch_user_ids, Loan.organization_id)
        uw = db.query(func.count(Loan.id).label('cnt'), func.avg(func.coalesce(Loan.days_in_stage, 0)).label('avg_days')).filter(*uw_filters).first()
        uw_perf = max(0, min(100, int(100 - max(0, (float(uw.avg_days or 0) - 7) * 5)))) if (uw.cnt or 0) > 0 else 0
        results.append({"role": "Underwriters", "performance": uw_perf})

        # Closer performance
        close_filters = [Loan.stage == LoanStage.FUNDED, Loan.funded_date >= cutoff.date()]
        _apply_scope(close_filters, Loan.loan_officer_id, user_id, org_id, branch_user_ids, Loan.organization_id)
        funded = db.query(func.count(Loan.id)).filter(*close_filters).scalar() or 0
        results.append({"role": "Closers", "performance": min(100, max(0, 75 + funded * 2)) if funded > 0 else 0})

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


# =============================================================================
# 12. Mortgages Under Management (MUM) Summary
# =============================================================================

def calculate_mum_summary(
    db: Session, user_id: int, org_id: int,
    branch_user_ids: Optional[list] = None,
) -> dict:
    """MUM portfolio: loan count, total volume, commission, annual return."""
    try:
        mum_filters = []
        _apply_scope(mum_filters, MUMClient.user_id, user_id, org_id, branch_user_ids, MUMClient.organization_id)

        result = db.query(
            func.count(MUMClient.id).label('loan_count'),
            func.sum(MUMClient.current_loan_amount).label('total_volume'),
            func.sum(MUMClient.original_loan_amount).label('total_original'),
            func.avg(MUMClient.interest_rate).label('avg_rate'),
        ).filter(*mum_filters).first()

        loan_count = result.loan_count or 0
        total_volume = round(result.total_volume or 0, 2)
        total_original = round(result.total_original or 0, 2)
        avg_rate = round(float(result.avg_rate or 0), 4)

        # Commission estimate: industry standard ~25 bps annually on servicing
        commission_bps = 25
        annual_commission = round(total_volume * commission_bps / 10000, 2) if total_volume > 0 else 0

        # Annual return: commission as % of original volume
        annual_return_pct = round(annual_commission / total_original * 100, 2) if total_original > 0 else 0

        return {
            "loan_count": loan_count,
            "total_volume": total_volume,
            "annual_commission": annual_commission,
            "annual_return_pct": annual_return_pct,
            "avg_rate": avg_rate,
        }
    except Exception as e:
        logger.error("calculate_mum_summary failed: %s", e)
        db.rollback()
        return {"loan_count": 0, "total_volume": 0, "annual_commission": 0, "annual_return_pct": 0, "avg_rate": 0}
