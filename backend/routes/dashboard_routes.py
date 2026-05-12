"""
Dashboard API Routes
====================

Provides the main dashboard endpoint with comprehensive metrics including:
- Pipeline statistics (leads by stage, loans by stage)
- Production metrics (goals vs actuals)
- Lead metrics and alerts
- Referral partner stats
- Team stats
- Efficiency metrics (time to close, pull-through rate, bottlenecks)

These metrics are server-computed from CRM database and cached for performance.

Enterprise Readiness (Check 9.6):
Role-based access scoping is applied via middleware/report_access.py.
Scope information is included in the response for client awareness.
"""

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, extract, case, text

# Runtime imports — use standalone modules to avoid circular imports with main.py
from auth.dependencies import get_current_user
from database import get_db
from database.enums import LeadStage, LoanStage
from database.models import User, Lead, Loan, Task, ReferralPartner, AIColleagueAction, Notification
from performance_cache import get_cached, set_cached, run_parallel_sync, DASHBOARD_TTL
from database import SessionLocal
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
    calculate_mum_summary,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Dashboard"])


# =============================================================================
# DASHBOARD ENDPOINT
# =============================================================================

@router.get("/dashboard")
async def get_dashboard(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get dashboard data with real metrics from database.
    All values are server-computed from CRM database.
    OPTIMIZED: Uses caching + fewer queries by batching and aggregating in memory.

    Query Parameters:
    - start_date: Optional date range start (YYYY-MM-DD). Defaults to 30 days ago.
    - end_date: Optional date range end (YYYY-MM-DD). Defaults to today.

    Enterprise Readiness (Check 9.6 - Branch-Level Access):
    Branch managers can only see data from loan officers in their branch.

    Enterprise Readiness (Check 9.14 - Dashboard Date Range):
    Supports configurable date ranges instead of hardcoded 30 days.
    """
    # Default dashboard data for error cases
    default_dashboard = {
        "prioritized_tasks": [],
        "pipeline_stats": [
            {"id": "new", "name": "New Leads", "count": 0, "alerts": 0, "alert_text": "", "volume": None},
            {"id": "preapproved", "name": "Pre-Approved", "count": 0, "alerts": 0, "alert_text": "", "volume": None},
            {"id": "processing", "name": "In Processing", "count": 0, "alerts": 0, "alert_text": "", "volume": 0},
            {"id": "underwriting", "name": "In Underwriting", "count": 0, "alerts": 0, "alert_text": "", "volume": 0},
            {"id": "ctc", "name": "Clear to Close", "count": 0, "alerts": 0, "alert_text": "", "volume": 0},
            {"id": "closing", "name": "Closing", "count": 0, "alerts": 0, "alert_text": "", "volume": 0},
            {"id": "funded", "name": "Funded This Month", "count": 0, "alerts": 0, "alert_text": "", "volume": 0}
        ],
        "production": {
            "annualGoal": 0, "annualActual": 0, "annualProgress": 0,
            "monthlyGoal": 0, "monthlyActual": 0, "monthlyProgress": 0,
            "weeklyGoal": 0, "weeklyActual": 0, "weeklyProgress": 0,
            "dailyGoal": 0, "dailyActual": 0, "dailyProgress": 0
        },
        "lead_metrics": {"new_today": 0, "avg_contact_time": 0, "conversion_rate": 0, "hot_leads": 0, "alerts": []},
        "loan_issues": [],
        "ai_tasks": {"pending": [], "waiting": []},
        "referral_stats": {"top_partners": [], "engagement": []},
        "team_stats": {"has_team": False, "avg_workload": 0, "backlog": 0, "sla_missed": 0, "insights": []},
        "messages": [],
        "mum_summary": {"loan_count": 0, "total_volume": 0, "annual_commission": 0, "annual_return_pct": 0, "avg_rate": 0},
        "efficiency": {
            "overallScore": 0, "trend": "stable",
            "avgTimeToClose": 0, "avgTimeToCloseChange": 0,
            "pullThroughRate": 0, "pullThroughRateChange": 0,
            "loansFallingBehind": 0, "loansFallingBehindChange": 0,
            "automationRate": 0, "automationRateChange": 0,
            "customerSatisfaction": None, "customerSatisfactionChange": 0,
            "stages": [], "team": [], "bottleneckCount": 0, "bottlenecks": []
        }
    }

    # Parse date range (Check 9.14)
    if start_date and end_date:
        try:
            from datetime import datetime as dt
            start_dt = dt.strptime(start_date, "%Y-%m-%d").date()
            end_dt = dt.strptime(end_date, "%Y-%m-%d").date()
            thirty_days_ago = start_dt
            today = end_dt
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
    else:
        # Default: last 30 days
        today = date.today()
        thirty_days_ago = today - timedelta(days=30)

    # Check cache first for blazing fast retrieval (include date range in key)
    cache_key = f"dashboard:{current_user.id}:{thirty_days_ago}:{today}"
    cached_data = get_cached(cache_key)
    if cached_data:
        return cached_data

    # Organization-scoped filtering (Enterprise Readiness Check 9.5-9.7)
    # TENANT-008: Require organization context — dashboard must never return unscoped data
    org_id = getattr(current_user, 'organization_id', None)
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization context required")

    # Branch-level access control (Enterprise Readiness Check 9.6)
    # Since Lead/Loan models don't have branch_id, we filter via User.branch_id
    from middleware.report_access import get_report_scope
    scope = get_report_scope(current_user)
    branch_user_ids = None

    if scope["scope"] == "branch":
        # Branch manager: get all users in their branch
        branch_id = scope.get("branch_id")
        if branch_id:
            branch_users = db.query(User.id).filter(User.branch_id == branch_id).all()
            branch_user_ids = [u.id for u in branch_users]
    elif scope["scope"] == "user":
        # Individual user: only their own data
        branch_user_ids = [current_user.id]

    # Verify database tables exist before proceeding
    try:
        # Quick check if core tables are accessible
        db.execute(text("SELECT 1 FROM loans LIMIT 1"))
    except Exception as table_err:
        logger.warning(f"Dashboard: loans table not accessible ({table_err}), returning defaults")
        return default_dashboard

    # Get current date ranges
    today = date.today()
    start_of_month = today.replace(day=1)
    start_of_week = today - timedelta(days=today.weekday())
    start_of_year = today.replace(month=1, day=1)

    # ============================================================================
    # PARALLEL METRIC CALCULATIONS
    # Each function gets its own DB session for thread safety.
    # ============================================================================

    user_metadata = current_user.user_metadata or {}
    uid = current_user.id

    def _with_session(func, *args, **kwargs):
        """Run a metric function with a fresh DB session, closing it after."""
        session = SessionLocal()
        try:
            return func(session, *args, **kwargs)
        finally:
            session.close()

    (
        production,
        pipeline_stats,
        lead_metrics,
        team_stats,
        loan_issues,
        profitability,
        mum_summary,
        eff_summary,
        trends,
        bottleneck_list,
    ) = run_parallel_sync(
        (lambda: _with_session(calculate_production_metrics, uid, org_id, branch_user_ids=branch_user_ids, user_metadata=user_metadata), ()),
        (lambda: _with_session(calculate_pipeline_stats, uid, org_id, branch_user_ids=branch_user_ids), ()),
        (lambda: _with_session(calculate_lead_metrics, uid, org_id, branch_user_ids=branch_user_ids), ()),
        (lambda: _with_session(calculate_team_stats, uid, org_id, branch_user_ids=branch_user_ids), ()),
        (lambda: _with_session(calculate_loan_issues, uid, org_id, branch_user_ids=branch_user_ids), ()),
        (lambda: _with_session(calculate_profitability, uid, org_id, branch_user_ids=branch_user_ids), ()),
        (lambda: _with_session(calculate_mum_summary, uid, org_id, branch_user_ids=branch_user_ids), ()),
        (lambda: _with_session(calculate_efficiency_summary, uid, org_id, branch_user_ids=branch_user_ids), ()),
        (lambda: _with_session(calculate_efficiency_trends, uid, org_id, branch_user_ids=branch_user_ids), ()),
        (lambda: _with_session(calculate_bottlenecks, uid, org_id, branch_user_ids=branch_user_ids), ()),
    )

    # Handle errors from parallel execution (run_parallel_sync returns {"error": ...} on failure)
    if isinstance(production, dict) and "error" in production:
        production = {"annualGoal": 0, "annualActual": 0, "annualProgress": 0, "monthlyGoal": 0, "monthlyActual": 0, "monthlyProgress": 0, "weeklyGoal": 0, "weeklyActual": 0, "weeklyProgress": 0, "dailyGoal": 0, "dailyActual": 0, "dailyProgress": 0}
    if isinstance(pipeline_stats, dict) and "error" in pipeline_stats:
        pipeline_stats = default_dashboard["pipeline_stats"]
    if isinstance(lead_metrics, dict) and "error" in lead_metrics:
        lead_metrics = default_dashboard["lead_metrics"]
    if isinstance(team_stats, dict) and "error" in team_stats:
        team_stats = default_dashboard["team_stats"]
    if isinstance(loan_issues, dict) and "error" in loan_issues:
        loan_issues = []
    if isinstance(profitability, dict) and "error" in profitability:
        profitability = {"funded_ytd": 0, "total_volume": 0, "avg_loan_size": 0, "gain_on_sale": 0, "revenue_per_loan": 0, "insights": []}
    if isinstance(mum_summary, dict) and "error" in mum_summary:
        mum_summary = default_dashboard["mum_summary"]
    if isinstance(eff_summary, dict) and "error" in eff_summary:
        eff_summary = {"overallScore": 0, "avgTimeToClose": 0, "pullThroughRate": 0, "loansFallingBehind": 0, "automationRate": 0}
    if isinstance(trends, dict) and "error" in trends:
        trends = {"overall_trend": 0, "time_to_close_change": 0, "pull_through_change": 0, "loans_behind_change": 0, "automation_change": 0}
    if isinstance(bottleneck_list, dict) and "error" in bottleneck_list:
        bottleneck_list = []

    total_loan_count_from_pipeline = sum(s.get("count", 0) for s in pipeline_stats if s["id"] not in ("new", "preapproved", "funded"))

    # ============================================================================
    # TASKS FOR TODAY
    # ============================================================================

    try:
        query_filters = [
            Task.status.in_(["pending", "in_progress"]),
            Task.due_date <= today + timedelta(days=1)
        ]
        if org_id:
            query_filters.append(Task.organization_id == org_id)
        if branch_user_ids is not None:
            query_filters.append(Task.owner_id.in_(branch_user_ids))
        else:
            query_filters.append(Task.owner_id == current_user.id)

        tasks_today = db.query(Task).filter(*query_filters).order_by(Task.priority.desc(), Task.due_date).limit(10).all()

        prioritized_tasks = [{
            "title": task.title,
            "borrower": task.related_contact_name,
            "stage": task.related_type,
            "urgency": task.priority,
            "ai_action": None
        } for task in tasks_today]
    except Exception as task_err:
        logger.warning(f"Dashboard: Error getting tasks: {task_err}")
        prioritized_tasks = []

    # ============================================================================
    # REFERRAL PARTNER STATS
    # ============================================================================

    try:
        # OPTIMIZED: Get partners and their lead counts in separate queries, then join in memory
        # NOTE: ReferralPartners are shared resources without ownership
        partners = db.query(ReferralPartner).filter(
            ReferralPartner.status == "active"
        ).limit(5).all()

        # Get lead counts by referral_partner_id FK
        partner_ids = [p.id for p in partners]
        if partner_ids:
            query_filters = [Lead.referral_partner_id.in_(partner_ids)]
            if org_id:
                query_filters.append(Lead.organization_id == org_id)
            if branch_user_ids is not None:
                query_filters.append(Lead.owner_id.in_(branch_user_ids))
            else:
                query_filters.append(Lead.owner_id == current_user.id)

            lead_counts_by_partner = db.query(
                Lead.referral_partner_id,
                func.count(Lead.id).label('count')
            ).filter(*query_filters).group_by(Lead.referral_partner_id).all()

            # Create a lookup dict keyed by partner id
            partner_counts = {row.referral_partner_id: row.count for row in lead_counts_by_partner}
        else:
            partner_counts = {}

        referral_stats = {
            "top_partners": [{
                "name": p.name,
                "received": partner_counts.get(p.id, 0),
                "sent": p.referrals_out or 0,
                "balance": (partner_counts.get(p.id, 0)) - (p.referrals_out or 0)
            } for p in partners],
            "engagement": []
        }
    except Exception as referral_err:
        logger.warning(f"Dashboard: Error getting referral stats: {referral_err}")
        referral_stats = {"top_partners": [], "engagement": []}

    # ============================================================================
    # WORKFLOW SCORES (real loan stage health)
    # ============================================================================

    try:
        workflow_stage_configs = [
            {"id": "application", "name": "Application", "stages": [LoanStage.APPLICATION, LoanStage.DISCLOSED], "target_days": 7},
            {"id": "processing", "name": "Processing", "stages": [LoanStage.PROCESSING], "target_days": 10},
            {"id": "submitted", "name": "Submitted to UW", "stages": [LoanStage.SUBMITTED], "target_days": 3},
            {"id": "underwriting", "name": "Underwriting", "stages": [LoanStage.UNDERWRITING, LoanStage.UW_RECEIVED], "target_days": 7},
            {"id": "conditional", "name": "Conditional Approval", "stages": [LoanStage.CONDITIONAL_APPROVAL], "target_days": 5},
            {"id": "ctc", "name": "Clear to Close", "stages": [LoanStage.CTC, LoanStage.CLEAR_TO_CLOSE, LoanStage.APPROVED], "target_days": 3},
            {"id": "closing", "name": "Closing & Docs", "stages": [LoanStage.CLOSING, LoanStage.DOCS, LoanStage.DOCS_OUT], "target_days": 5},
        ]

        # Compute task counts once (not stage-specific) to avoid N+1 queries
        task_due_filters = [
            Task.status.in_(["pending", "in_progress"]),
            Task.organization_id == org_id
        ]
        if branch_user_ids is not None:
            task_due_filters.append(Task.owner_id.in_(branch_user_ids))
        else:
            task_due_filters.append(Task.owner_id == current_user.id)
        wf_tasks_due = db.query(func.count(Task.id)).filter(*task_due_filters).scalar() or 0

        task_completed_filters = [
            Task.organization_id == org_id,
            Task.status == "completed",
            Task.completed_at >= thirty_days_ago
        ]
        if branch_user_ids is not None:
            task_completed_filters.append(Task.owner_id.in_(branch_user_ids))
        else:
            task_completed_filters.append(Task.owner_id == current_user.id)
        wf_tasks_completed = db.query(func.count(Task.id)).filter(*task_completed_filters).scalar() or 0

        # Single aggregation query for all stage metrics
        all_stages_flat = []
        for cfg in workflow_stage_configs:
            all_stages_flat.extend(cfg["stages"])

        wf_base_filters = [Loan.stage.in_(all_stages_flat)]
        if org_id:
            wf_base_filters.append(Loan.organization_id == org_id)
        if branch_user_ids is not None:
            wf_base_filters.append(Loan.loan_officer_id.in_(branch_user_ids))
        else:
            wf_base_filters.append(Loan.loan_officer_id == current_user.id)

        stage_agg_rows = db.query(
            Loan.stage,
            func.count(Loan.id).label('cnt'),
            func.avg(func.coalesce(Loan.days_in_stage, 0)).label('avg_days')
        ).filter(*wf_base_filters).group_by(Loan.stage).all()

        stage_agg = {}
        for row in stage_agg_rows:
            stage_agg[row.stage] = {"cnt": row.cnt or 0, "avg_days": row.avg_days or 0}

        workflow_statuses = []
        total_workflow_score = 0

        for wf_config in workflow_stage_configs:
            active_loans = sum(stage_agg.get(s, {}).get("cnt", 0) for s in wf_config["stages"])
            total_days = sum(
                stage_agg.get(s, {}).get("avg_days", 0) * stage_agg.get(s, {}).get("cnt", 0)
                for s in wf_config["stages"]
            )
            avg_days = (total_days / active_loans) if active_loans > 0 else 0

            stage_score = max(0, min(100, int(100 - max(0, (avg_days - wf_config["target_days"]) * 10))))
            health = "good" if stage_score >= 80 else ("warning" if stage_score >= 60 else "critical")

            workflow_statuses.append({
                "id": wf_config["id"],
                "name": wf_config["name"],
                "score": stage_score,
                "health": health,
                "activeLoans": active_loans,
                "tasksDue": wf_tasks_due,
                "tasksCompleted": wf_tasks_completed
            })
            total_workflow_score += stage_score

        overall_workflow_score = int(total_workflow_score / len(workflow_stage_configs)) if workflow_stage_configs else 0

        workflow_scores = {
            "statuses": workflow_statuses,
            "overallScore": overall_workflow_score
        }
    except Exception as wf_err:
        logger.warning(f"Dashboard: Error getting workflow scores: {wf_err}")
        workflow_scores = {"statuses": [], "overallScore": 0}

    # ============================================================================
    # AI TASKS (real AIColleagueAction data)
    # ============================================================================

    try:
        ai_action_filters = [AIColleagueAction.status == "pending"]
        if org_id:
            ai_action_filters.append(AIColleagueAction.organization_id == org_id)
        if branch_user_ids is not None:
            ai_action_filters.append(AIColleagueAction.user_id.in_(branch_user_ids))
        else:
            ai_action_filters.append(AIColleagueAction.user_id == current_user.id)

        pending_actions = db.query(AIColleagueAction).filter(
            *ai_action_filters,
            AIColleagueAction.executed_at.is_(None)
        ).order_by(AIColleagueAction.created_at.desc()).limit(10).all()

        waiting_actions = db.query(AIColleagueAction).filter(
            *ai_action_filters,
            AIColleagueAction.required_approval == True,
            AIColleagueAction.approved_at.is_(None)
        ).order_by(AIColleagueAction.created_at.desc()).limit(10).all()

        waiting_ids = {a.id for a in waiting_actions}
        pending_only = [a for a in pending_actions if a.id not in waiting_ids]

        ai_tasks_data = {
            "pending": [{
                "id": a.id,
                "action_type": a.action_type,
                "agent_name": a.agent_name,
                "reasoning": (a.reasoning or "")[:120],
                "confidence": a.confidence_score,
                "created_at": a.created_at.isoformat() if a.created_at else None
            } for a in pending_only[:5]],
            "waiting": [{
                "id": a.id,
                "action_type": a.action_type,
                "agent_name": a.agent_name,
                "reasoning": (a.reasoning or "")[:120],
                "confidence": a.confidence_score,
                "created_at": a.created_at.isoformat() if a.created_at else None
            } for a in waiting_actions[:5]]
        }
    except Exception as ai_err:
        logger.warning(f"Dashboard: Error getting AI tasks: {ai_err}")
        ai_tasks_data = {"pending": [], "waiting": []}

    # ============================================================================
    # MESSAGES (recent notifications for this user)
    # ============================================================================

    try:
        notif_filters = [Notification.user_id == current_user.id]
        if org_id:
            notif_filters.append(
                (Notification.organization_id == org_id) | (Notification.organization_id.is_(None))
            )

        recent_notifs = db.query(Notification).filter(
            *notif_filters
        ).order_by(Notification.created_at.desc()).limit(10).all()

        messages = [
            {
                "id": n.id,
                "type": n.type,
                "title": n.title,
                "message": n.message,
                "link": n.link,
                "read": n.is_read,
                "created_at": n.created_at.isoformat() if n.created_at else None
            }
            for n in recent_notifs
        ]
    except Exception as msg_err:
        logger.warning(f"Dashboard: Error getting messages: {msg_err}")
        messages = []

    # ============================================================================
    # EFFICIENCY METRICS (stage_perf / team_perf depend on total_loan_count)
    # ============================================================================

    total_loan_count = total_loan_count_from_pipeline

    if total_loan_count > 0:
        (stage_perf, team_perf) = run_parallel_sync(
            (lambda: _with_session(calculate_stage_performance, uid, org_id, branch_user_ids=branch_user_ids), ()),
            (lambda: _with_session(calculate_team_performance, uid, org_id, branch_user_ids=branch_user_ids), ()),
        )
        if isinstance(stage_perf, dict) and "error" in stage_perf:
            stage_perf = []
        if isinstance(team_perf, dict) and "error" in team_perf:
            team_perf = []
    else:
        stage_perf = []
        team_perf = []

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

    # Add role-based scope info (Enterprise Readiness Check 9.6)
    try:
        from middleware.report_access import get_report_scope, get_scope_description
        scope = get_report_scope(current_user)
        scope_info = get_scope_description(scope)
    except Exception as e:
        logger.error(f"Error in get_dashboard (scope_info): {e}")
        scope_info = "Personal data"

    result = {
        "scope": scope_info,
        "prioritized_tasks": prioritized_tasks,
        "pipeline_stats": pipeline_stats,
        "production": production,
        "lead_metrics": lead_metrics,
        "loan_issues": loan_issues,
        "ai_tasks": ai_tasks_data,
        "referral_stats": referral_stats,
        "team_stats": team_stats,
        "messages": messages,
        "efficiency": efficiency,
        "workflow_scores": workflow_scores,
        "profitability": profitability,
        "mum_summary": mum_summary
    }

    # Cache for blazing fast retrieval on subsequent requests
    set_cached(cache_key, result, ttl=DASHBOARD_TTL)
    return result
