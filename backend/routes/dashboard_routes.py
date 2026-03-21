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
from database.models import User, Lead, Loan, Task, ReferralPartner, AIColleagueAction
from performance_cache import get_cached, set_cached

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Dashboard"])


# =============================================================================
# DASHBOARD HELPER FUNCTIONS
# =============================================================================

def calculate_stage_performance(db: Session, user_id: int, thirty_days_ago, org_id: Optional[int] = None, branch_user_ids: Optional[list] = None) -> list:
    """
    Calculate real stage performance metrics based on actual loan data.
    Returns efficiency scores and status for each stage.

    Args:
        branch_user_ids: List of user IDs in the branch (for branch-level filtering).
                         If None, uses user_id. If empty list, uses all org users.
    """
    # Define stage mapping with target days for each stage
    stage_configs = [
        {"name": "Lead Generation", "stages": [LeadStage.NEW], "type": "lead", "target_days": 2},
        {"name": "Pre-Qualification", "stages": [LeadStage.ATTEMPTED_CONTACT, LeadStage.PRE_QUALIFIED], "type": "lead", "target_days": 5},
        {"name": "Application", "stages": [LeadStage.APPLICATION], "type": "lead", "target_days": 7},
        {"name": "Processing", "stages": [LoanStage.PROCESSING], "type": "loan", "target_days": 10},
        {"name": "Underwriting", "stages": [LoanStage.SUBMITTED, LoanStage.UW_RECEIVED, LoanStage.UNDERWRITING], "type": "loan", "target_days": 7},
        {"name": "Clear to Close", "stages": [LoanStage.CTC], "type": "loan", "target_days": 3},
        {"name": "Closing", "stages": [LoanStage.DOCS_OUT, LoanStage.FUNDED], "type": "loan", "target_days": 5}
    ]

    now = datetime.now(timezone.utc)
    stage_results = []

    for config in stage_configs:
        if config["type"] == "lead":
            # Query leads in these stages
            query_filters = [Lead.stage.in_(config["stages"])]
            if org_id:
                query_filters.append(Lead.organization_id == org_id)
            if branch_user_ids is not None:
                query_filters.append(Lead.owner_id.in_(branch_user_ids))
            else:
                query_filters.append(Lead.owner_id == user_id)

            leads_in_stage = db.query(Lead).filter(*query_filters).all()

            if leads_in_stage:
                total_days = 0
                count = 0
                for lead in leads_in_stage:
                    if lead.stage_changed_at:
                        days_in_stage = (now - lead.stage_changed_at).days
                        total_days += days_in_stage
                        count += 1
                    elif lead.created_at:
                        days_in_stage = (now - lead.created_at).days
                        total_days += days_in_stage
                        count += 1

                avg_days = total_days / count if count > 0 else 0
                # Calculate efficiency: 100% if at or below target, decreases linearly
                efficiency = max(0, min(100, int(100 - max(0, (avg_days - config["target_days"]) * 10))))
            else:
                efficiency = 100  # No items = no delays
                avg_days = 0
        else:
            # Query loans in these stages
            query_filters = [Loan.stage.in_(config["stages"])]
            if org_id:
                query_filters.append(Loan.organization_id == org_id)
            if branch_user_ids is not None:
                query_filters.append(Loan.loan_officer_id.in_(branch_user_ids))
            else:
                query_filters.append(Loan.loan_officer_id == user_id)

            loans_in_stage = db.query(Loan).filter(*query_filters).all()

            if loans_in_stage:
                total_days = 0
                count = 0
                for loan in loans_in_stage:
                    if loan.days_in_stage:
                        total_days += loan.days_in_stage
                        count += 1
                    elif loan.created_at:
                        days_in_stage = (now - loan.created_at).days
                        total_days += days_in_stage
                        count += 1

                avg_days = total_days / count if count > 0 else 0
                efficiency = max(0, min(100, int(100 - max(0, (avg_days - config["target_days"]) * 10))))
            else:
                efficiency = 100
                avg_days = 0

        # Determine status based on efficiency
        if efficiency >= 80:
            status = "on-track"
        elif efficiency >= 60:
            status = "slightly-delayed"
        else:
            status = "behind"

        stage_results.append({
            "name": config["name"],
            "efficiency": efficiency,
            "status": status
        })

    return stage_results


def calculate_team_performance(db: Session, user_id: int, thirty_days_ago, org_id: Optional[int] = None, branch_user_ids: Optional[list] = None) -> list:
    """
    Calculate real team performance metrics based on actual user roles and their metrics.
    Returns performance scores by role category.

    Args:
        branch_user_ids: List of user IDs in the branch (for branch-level filtering).
    """
    # Get the user's organization or team context
    current_user = db.query(User).filter(User.id == user_id).first()
    if not current_user:
        return []

    team_results = []

    # Loan Officers performance - based on conversion rate and volume
    query_filters = [Lead.created_at >= thirty_days_ago]
    if org_id:
        query_filters.append(Lead.organization_id == org_id)
    if branch_user_ids is not None:
        query_filters.append(Lead.owner_id.in_(branch_user_ids))
    else:
        query_filters.append(Lead.owner_id == user_id)

    lo_metrics = db.query(
        func.count(Lead.id).label('total_leads'),
        func.count(func.nullif(Lead.stage == LeadStage.CLOSED, False)).label('converted')
    ).filter(*query_filters).first()

    total_leads = lo_metrics.total_leads or 0
    converted = lo_metrics.converted or 0
    lo_conversion = (converted / total_leads * 100) if total_leads > 0 else 0
    # Scale to performance: 20% conversion = 80 performance, adjust proportionally
    lo_performance = min(100, max(0, int(60 + lo_conversion * 2)))

    team_results.append({"role": "Loan Officers", "performance": lo_performance})

    # Processors performance - based on processing time
    query_filters = [Loan.stage == LoanStage.PROCESSING]
    if org_id:
        query_filters.append(Loan.organization_id == org_id)
    if branch_user_ids is not None:
        query_filters.append(Loan.loan_officer_id.in_(branch_user_ids))
    else:
        query_filters.append(Loan.loan_officer_id == user_id)

    processing_loans = db.query(Loan).filter(*query_filters).all()

    if processing_loans:
        avg_processing_days = sum(
            loan.days_in_stage or 0 for loan in processing_loans
        ) / len(processing_loans)
        # Target: 10 days for processing, scale inversely
        processor_performance = max(0, min(100, int(100 - max(0, (avg_processing_days - 10) * 5))))
    else:
        processor_performance = 85  # Default if no data

    team_results.append({"role": "Processors", "performance": processor_performance})

    # Underwriters performance - based on underwriting time
    query_filters = [Loan.stage.in_([LoanStage.UW_RECEIVED, LoanStage.UNDERWRITING])]
    if org_id:
        query_filters.append(Loan.organization_id == org_id)
    if branch_user_ids is not None:
        query_filters.append(Loan.loan_officer_id.in_(branch_user_ids))
    else:
        query_filters.append(Loan.loan_officer_id == user_id)

    uw_loans = db.query(Loan).filter(*query_filters).all()

    if uw_loans:
        avg_uw_days = sum(
            loan.days_in_stage or 0 for loan in uw_loans
        ) / len(uw_loans)
        # Target: 7 days for underwriting
        uw_performance = max(0, min(100, int(100 - max(0, (avg_uw_days - 7) * 5))))
    else:
        uw_performance = 80  # Default if no data

    team_results.append({"role": "Underwriters", "performance": uw_performance})

    # Closers performance - based on CTC to funding time
    query_filters = [
        Loan.stage == LoanStage.FUNDED,
        Loan.funded_date >= thirty_days_ago
    ]
    if org_id:
        query_filters.append(Loan.organization_id == org_id)
    if branch_user_ids is not None:
        query_filters.append(Loan.loan_officer_id.in_(branch_user_ids))
    else:
        query_filters.append(Loan.loan_officer_id == user_id)

    funded_loans = db.query(Loan).filter(*query_filters).all()

    if funded_loans:
        # Closers are performing well if loans get funded promptly
        closer_performance = min(100, max(0, 75 + len(funded_loans) * 2))
    else:
        closer_performance = 85  # Default if no data

    team_results.append({"role": "Closers", "performance": closer_performance})

    return team_results


def calculate_bottlenecks(db: Session, user_id: int, org_id: Optional[int] = None, branch_user_ids: Optional[list] = None) -> list:
    """
    Calculate real bottlenecks based on actual loan issues and delays.
    Returns dynamic bottleneck data with real affected counts and delays.

    Args:
        branch_user_ids: List of user IDs in the branch (for branch-level filtering).
    """
    now = datetime.now(timezone.utc)
    bottlenecks = []

    # 1. Check for loans missing documents (stuck in processing)
    query_filters = [
        Loan.stage == LoanStage.PROCESSING,
        Loan.days_in_stage > 10
    ]
    if org_id:
        query_filters.append(Loan.organization_id == org_id)
    if branch_user_ids is not None:
        query_filters.append(Loan.loan_officer_id.in_(branch_user_ids))
    else:
        query_filters.append(Loan.loan_officer_id == user_id)

    processing_loans = db.query(Loan).filter(*query_filters).all()

    if processing_loans:
        avg_delay = sum(loan.days_in_stage or 0 for loan in processing_loans) / len(processing_loans)
        bottlenecks.append({
            "issue": "Loans Delayed in Processing",
            "stage": "Processing",
            "affectedLoans": len(processing_loans),
            "avgDelay": f"{round(avg_delay, 1)} days"
        })

    # 2. Check for leads stuck without contact
    query_filters = [
        Lead.stage == LeadStage.NEW,
        Lead.created_at < now - timedelta(days=3)
    ]
    if org_id:
        query_filters.append(Lead.organization_id == org_id)
    if branch_user_ids is not None:
        query_filters.append(Lead.owner_id.in_(branch_user_ids))
    else:
        query_filters.append(Lead.owner_id == user_id)

    stuck_leads = db.query(func.count(Lead.id)).filter(*query_filters).scalar() or 0

    if stuck_leads > 0:
        bottlenecks.append({
            "issue": "Leads Awaiting Initial Contact",
            "stage": "Lead Generation",
            "affectedLoans": stuck_leads,
            "avgDelay": ">3 days"
        })

    # 3. Check for underwriting delays
    query_filters = [
        Loan.stage.in_([LoanStage.UW_RECEIVED, LoanStage.UNDERWRITING]),
        Loan.days_in_stage > 7
    ]
    if org_id:
        query_filters.append(Loan.organization_id == org_id)
    if branch_user_ids is not None:
        query_filters.append(Loan.loan_officer_id.in_(branch_user_ids))
    else:
        query_filters.append(Loan.loan_officer_id == user_id)

    uw_delays = db.query(Loan).filter(*query_filters).all()

    if uw_delays:
        avg_uw_delay = sum(loan.days_in_stage or 0 for loan in uw_delays) / len(uw_delays)
        bottlenecks.append({
            "issue": "Underwriting Taking Longer Than Expected",
            "stage": "Underwriting",
            "affectedLoans": len(uw_delays),
            "avgDelay": f"{round(avg_uw_delay, 1)} days"
        })

    # 4. Check for loans with rate lock expiring soon
    query_filters = [
        Loan.lock_expiration_date.isnot(None),
        Loan.lock_expiration_date <= now + timedelta(days=7),
        Loan.stage.not_in([LoanStage.FUNDED, LoanStage.CANCELLED, LoanStage.DENIED])
    ]
    if org_id:
        query_filters.append(Loan.organization_id == org_id)
    if branch_user_ids is not None:
        query_filters.append(Loan.loan_officer_id.in_(branch_user_ids))
    else:
        query_filters.append(Loan.loan_officer_id == user_id)

    rate_lock_expiring = db.query(func.count(Loan.id)).filter(*query_filters).scalar() or 0

    if rate_lock_expiring > 0:
        bottlenecks.append({
            "issue": "Rate Lock Expiring Soon",
            "stage": "All Active Stages",
            "affectedLoans": rate_lock_expiring,
            "avgDelay": "<7 days to expiry"
        })

    # 5. Check for application stage delays
    query_filters = [
        Lead.stage == LeadStage.APPLICATION,
        Lead.stage_changed_at < now - timedelta(days=14)
    ]
    if org_id:
        query_filters.append(Lead.organization_id == org_id)
    if branch_user_ids is not None:
        query_filters.append(Lead.owner_id.in_(branch_user_ids))
    else:
        query_filters.append(Lead.owner_id == user_id)

    app_delays = db.query(Lead).filter(*query_filters).all()

    if app_delays:
        avg_app_delay = sum(
            (now - lead.stage_changed_at).days
            for lead in app_delays
            if lead.stage_changed_at
        ) / len(app_delays) if app_delays else 0

        bottlenecks.append({
            "issue": "Applications Pending Completion",
            "stage": "Application",
            "affectedLoans": len(app_delays),
            "avgDelay": f"{round(avg_app_delay, 1)} days"
        })

    return bottlenecks


def calculate_efficiency_trends(db: Session, user_id: int, org_id: Optional[int] = None, branch_user_ids: Optional[list] = None) -> dict:
    """
    Calculate trend values by comparing current period to previous period.
    Returns percentage changes for key metrics.

    Args:
        branch_user_ids: List of user IDs in the branch (for branch-level filtering).
    """
    now = datetime.now(timezone.utc)
    thirty_days_ago = now - timedelta(days=30)
    sixty_days_ago = now - timedelta(days=60)

    # Current period metrics (last 30 days)
    query_filters = [
        Loan.stage == LoanStage.FUNDED,
        Loan.funded_date >= thirty_days_ago.date()
    ]
    if org_id:
        query_filters.append(Loan.organization_id == org_id)
    if branch_user_ids is not None:
        query_filters.append(Loan.loan_officer_id.in_(branch_user_ids))
    else:
        query_filters.append(Loan.loan_officer_id == user_id)

    current_funded = db.query(func.count(Loan.id)).filter(*query_filters).scalar() or 0

    query_filters = [Loan.created_at >= thirty_days_ago]
    if org_id:
        query_filters.append(Loan.organization_id == org_id)
    if branch_user_ids is not None:
        query_filters.append(Loan.loan_officer_id.in_(branch_user_ids))
    else:
        query_filters.append(Loan.loan_officer_id == user_id)

    current_total_apps = db.query(func.count(Loan.id)).filter(*query_filters).scalar() or 1

    current_pull_through = (current_funded / current_total_apps * 100) if current_total_apps > 0 else 0

    # Previous period metrics (30-60 days ago)
    query_filters = [
        Loan.stage == LoanStage.FUNDED,
        Loan.funded_date >= sixty_days_ago.date(),
        Loan.funded_date < thirty_days_ago.date()
    ]
    if org_id:
        query_filters.append(Loan.organization_id == org_id)
    if branch_user_ids is not None:
        query_filters.append(Loan.loan_officer_id.in_(branch_user_ids))
    else:
        query_filters.append(Loan.loan_officer_id == user_id)

    prev_funded = db.query(func.count(Loan.id)).filter(*query_filters).scalar() or 0

    query_filters = [
        Loan.created_at >= sixty_days_ago,
        Loan.created_at < thirty_days_ago
    ]
    if org_id:
        query_filters.append(Loan.organization_id == org_id)
    if branch_user_ids is not None:
        query_filters.append(Loan.loan_officer_id.in_(branch_user_ids))
    else:
        query_filters.append(Loan.loan_officer_id == user_id)

    prev_total_apps = db.query(func.count(Loan.id)).filter(*query_filters).scalar() or 1

    prev_pull_through = (prev_funded / prev_total_apps * 100) if prev_total_apps > 0 else 0

    # Calculate average time to close for both periods (use application_date with fallback)
    def _loan_days_to_close(loan):
        """Get days from application (or creation) to funding."""
        if not loan.funded_date:
            return None
        start = loan.application_date or loan.created_at
        if not start:
            return None
        funded_d = loan.funded_date.date() if hasattr(loan.funded_date, 'date') else loan.funded_date
        start_d = start.date() if hasattr(start, 'date') else start
        days = (funded_d - start_d).days
        return days if days > 0 else None

    query_filters = [
        Loan.stage == LoanStage.FUNDED,
        Loan.funded_date >= thirty_days_ago.date(),
    ]
    if org_id:
        query_filters.append(Loan.organization_id == org_id)
    if branch_user_ids is not None:
        query_filters.append(Loan.loan_officer_id.in_(branch_user_ids))
    else:
        query_filters.append(Loan.loan_officer_id == user_id)

    current_funded_loans = db.query(Loan).filter(*query_filters).all()

    current_days = [d for loan in current_funded_loans if (d := _loan_days_to_close(loan)) is not None]
    current_avg_time = sum(current_days) / len(current_days) if current_days else 0

    query_filters = [
        Loan.stage == LoanStage.FUNDED,
        Loan.funded_date >= sixty_days_ago.date(),
        Loan.funded_date < thirty_days_ago.date(),
    ]
    if org_id:
        query_filters.append(Loan.organization_id == org_id)
    if branch_user_ids is not None:
        query_filters.append(Loan.loan_officer_id.in_(branch_user_ids))
    else:
        query_filters.append(Loan.loan_officer_id == user_id)

    prev_funded_loans = db.query(Loan).filter(*query_filters).all()

    prev_days = [d for loan in prev_funded_loans if (d := _loan_days_to_close(loan)) is not None]
    prev_avg_time = sum(prev_days) / len(prev_days) if prev_days else 0

    # Calculate trend percentages
    def calc_change(current, previous):
        if previous == 0:
            return 0 if current == 0 else 100
        return round(((current - previous) / previous) * 100, 1)

    pull_through_change = calc_change(current_pull_through, prev_pull_through)
    # For time to close, negative change is good (faster)
    time_to_close_change = calc_change(prev_avg_time, current_avg_time) if current_avg_time > 0 else 0

    # Overall efficiency trend
    overall_trend = round((pull_through_change + time_to_close_change) / 2, 1)

    # Count loans falling behind for both periods
    query_filters = [
        Loan.stage.in_([LoanStage.PROCESSING, LoanStage.UW_RECEIVED]),
        Loan.days_in_stage > 14
    ]
    if org_id:
        query_filters.append(Loan.organization_id == org_id)
    if branch_user_ids is not None:
        query_filters.append(Loan.loan_officer_id.in_(branch_user_ids))
    else:
        query_filters.append(Loan.loan_officer_id == user_id)

    current_behind = db.query(func.count(Loan.id)).filter(*query_filters).scalar() or 0

    return {
        "overall_trend": overall_trend,
        "pull_through_change": pull_through_change,
        "time_to_close_change": time_to_close_change,
        "loans_behind_change": -current_behind if current_behind > 0 else 0,
        "automation_change": 0  # Would need historical AI action tracking
    }


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
            "annualGoal": 222, "annualActual": 0, "annualProgress": 0,
            "monthlyGoal": 18.5, "monthlyActual": 0, "monthlyProgress": 0,
            "weeklyGoal": 5, "weeklyActual": 0, "weeklyProgress": 0,
            "dailyGoal": 1, "dailyActual": 0, "dailyProgress": 0
        },
        "lead_metrics": {"new_today": 0, "avg_contact_time": 1.2, "conversion_rate": 0, "hot_leads": 0, "alerts": []},
        "loan_issues": [],
        "ai_tasks": {"pending": [], "waiting": []},
        "referral_stats": {"top_partners": [], "engagement": []},
        "team_stats": {"has_team": False, "avg_workload": 0, "backlog": 0, "sla_missed": 0, "insights": []},
        "messages": [],
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
    # PRODUCTION METRICS (Goals vs Actuals)
    # ============================================================================

    # Get goals from user metadata (stored from Goal Tracker)
    user_metadata = current_user.user_metadata or {}
    goals = user_metadata.get('goals', {})

    # OPTIMIZED: Single query to get all funded loan counts with CASE statements
    try:
        query_filters = [Loan.stage == LoanStage.FUNDED]
        if org_id:
            query_filters.append(Loan.organization_id == org_id)
        if branch_user_ids is not None:
            query_filters.append(Loan.loan_officer_id.in_(branch_user_ids))
        else:
            query_filters.append(Loan.loan_officer_id == current_user.id)

        funded_counts = db.query(
            func.count(case((extract('year', Loan.funded_date) == today.year, 1))).label('annual'),
            func.count(case((Loan.funded_date >= start_of_month, 1))).label('monthly'),
            func.count(case((Loan.funded_date >= start_of_week, 1))).label('weekly'),
            func.count(case((Loan.funded_date == today, 1))).label('daily')
        ).filter(*query_filters).first()

        annual_actual = funded_counts.annual or 0
        monthly_actual = funded_counts.monthly or 0
        weekly_actual = funded_counts.weekly or 0
        daily_actual = funded_counts.daily or 0
    except Exception as prod_err:
        logger.warning(f"Dashboard: Error getting production metrics: {prod_err}")
        annual_actual = monthly_actual = weekly_actual = daily_actual = 0

    # Use goals from Goal Tracker or defaults
    annual_goal = goals.get('annualGoal', 222)
    monthly_goal = goals.get('monthlyGoal', 18.5)
    weekly_goal = goals.get('weeklyGoal', 5)
    daily_goal = goals.get('dailyGoal', 1)

    production = {
        "annualGoal": annual_goal,
        "annualActual": annual_actual,
        "annualProgress": int((annual_actual / annual_goal * 100)) if annual_goal > 0 else 0,
        "monthlyGoal": monthly_goal,
        "monthlyActual": monthly_actual,
        "monthlyProgress": int((monthly_actual / monthly_goal * 100)) if monthly_goal > 0 else 0,
        "weeklyGoal": weekly_goal,
        "weeklyActual": weekly_actual,
        "weeklyProgress": int((weekly_actual / weekly_goal * 100)) if weekly_goal > 0 else 0,
        "dailyGoal": daily_goal,
        "dailyActual": daily_actual,
        "dailyProgress": int((daily_actual / daily_goal * 100)) if daily_goal > 0 else 0,
    }

    # ============================================================================
    # PIPELINE STATS (Real loan counts per stage)
    # ============================================================================

    pipeline_stats = []

    # OPTIMIZED: Single query to get all lead counts
    try:
        query_filters = []
        if org_id:
            query_filters.append(Lead.organization_id == org_id)
        if branch_user_ids is not None:
            query_filters.append(Lead.owner_id.in_(branch_user_ids))
        else:
            query_filters.append(Lead.owner_id == current_user.id)

        lead_counts = db.query(
            func.count(case((Lead.stage == LeadStage.NEW, 1))).label('new_leads'),
            func.count(case((
                (Lead.stage == LeadStage.NEW) &
                (Lead.created_at < datetime.now(timezone.utc) - timedelta(hours=24)), 1
            ))).label('uncontacted'),
            func.count(case((Lead.stage == LeadStage.PRE_APPROVED, 1))).label('preapproved')
        ).filter(*query_filters).first()

        new_leads = lead_counts.new_leads or 0
        uncontacted_alerts = lead_counts.uncontacted or 0
        preapproved = lead_counts.preapproved or 0
    except Exception as lead_err:
        logger.warning(f"Dashboard: Error getting lead counts: {lead_err}")
        new_leads = uncontacted_alerts = preapproved = 0

    pipeline_stats.append({
        "id": "new",
        "name": "New Leads",
        "count": new_leads,
        "alerts": uncontacted_alerts,
        "alert_text": "follow-ups needed" if uncontacted_alerts > 0 else "",
        "volume": None
    })

    pipeline_stats.append({
        "id": "preapproved",
        "name": "Pre-Approved",
        "count": preapproved,
        "alerts": 0,
        "alert_text": "",
        "volume": None
    })

    # OPTIMIZED: Fetch all active loans in one query and aggregate in memory
    # Query ALL non-terminal stages so no active loans are missed
    TERMINAL_STAGES = [
        LoanStage.FUNDED, LoanStage.CANCELLED, LoanStage.DENIED,
        LoanStage.DEAD, LoanStage.WITHDRAWN, LoanStage.DOES_NOT_QUALIFY,
        LoanStage.NURTURE,
    ]
    try:
        query_filters = [Loan.stage.notin_(TERMINAL_STAGES)]
        if org_id:
            query_filters.append(Loan.organization_id == org_id)
        if branch_user_ids is not None:
            query_filters.append(Loan.loan_officer_id.in_(branch_user_ids))
        else:
            query_filters.append(Loan.loan_officer_id == current_user.id)

        active_loans = db.query(Loan).filter(*query_filters).all()

        # Bucket loans into pipeline categories
        processing_stages = {LoanStage.APPLICATION, LoanStage.DISCLOSED, LoanStage.PROCESSING}
        underwriting_stages = {LoanStage.SUBMITTED, LoanStage.UNDERWRITING, LoanStage.UW_RECEIVED, LoanStage.CONDITIONAL_APPROVAL}
        ctc_stages = {LoanStage.CTC, LoanStage.CLEAR_TO_CLOSE, LoanStage.APPROVED}
        closing_stages = {LoanStage.CLOSING, LoanStage.DOCS, LoanStage.DOCS_OUT}

        processing = [l for l in active_loans if l.stage in processing_stages]
        underwriting = [l for l in active_loans if l.stage in underwriting_stages]
        ctc = [l for l in active_loans if l.stage in ctc_stages]
        closing = [l for l in active_loans if l.stage in closing_stages]

        processing_volume = sum(loan.amount for loan in processing if loan.amount)
        processing_alerts = sum(1 for loan in processing if loan.days_in_stage and loan.days_in_stage > 14)

        underwriting_volume = sum(loan.amount for loan in underwriting if loan.amount)
        underwriting_alerts = sum(1 for loan in underwriting if loan.stage == LoanStage.SUSPENDED)

        ctc_volume = sum(loan.amount for loan in ctc if loan.amount)
        closing_volume = sum(loan.amount for loan in closing if loan.amount)
    except Exception as loan_err:
        logger.warning(f"Dashboard: Error getting active loans: {loan_err}")
        processing = underwriting = ctc = closing = []
        processing_volume = underwriting_volume = ctc_volume = closing_volume = 0
        processing_alerts = underwriting_alerts = 0

    pipeline_stats.append({
        "id": "processing",
        "name": "In Processing",
        "count": len(processing),
        "alerts": processing_alerts,
        "alert_text": "delayed" if processing_alerts > 0 else "",
        "volume": int(processing_volume)
    })

    pipeline_stats.append({
        "id": "underwriting",
        "name": "In Underwriting",
        "count": len(underwriting),
        "alerts": underwriting_alerts,
        "alert_text": "suspended" if underwriting_alerts > 0 else "",
        "volume": int(underwriting_volume)
    })

    pipeline_stats.append({
        "id": "ctc",
        "name": "Clear to Close",
        "count": len(ctc),
        "alerts": 0,
        "alert_text": "",
        "volume": int(ctc_volume)
    })

    pipeline_stats.append({
        "id": "closing",
        "name": "Closing",
        "count": len(closing),
        "alerts": 0,
        "alert_text": "",
        "volume": int(closing_volume)
    })

    # Funded this month - use aggregation
    try:
        query_filters = [
            Loan.stage == LoanStage.FUNDED,
            Loan.funded_date >= start_of_month
        ]
        if org_id:
            query_filters.append(Loan.organization_id == org_id)
        if branch_user_ids is not None:
            query_filters.append(Loan.loan_officer_id.in_(branch_user_ids))
        else:
            query_filters.append(Loan.loan_officer_id == current_user.id)

        funded_data = db.query(
            func.count(Loan.id).label('count'),
            func.sum(Loan.amount).label('volume')
        ).filter(*query_filters).first()
        funded_count = funded_data.count or 0
        funded_volume = int(funded_data.volume or 0)
    except Exception as funded_err:
        logger.warning(f"Dashboard: Error getting funded data: {funded_err}")
        funded_count = funded_volume = 0

    pipeline_stats.append({
        "id": "funded",
        "name": "Funded This Month",
        "count": funded_count,
        "alerts": 0,
        "alert_text": "",
        "volume": funded_volume
    })

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
    # LEAD METRICS & ALERTS
    # ============================================================================

    try:
        # OPTIMIZED: Single query for all lead metrics
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0)
        query_filters = []
        if org_id:
            query_filters.append(Lead.organization_id == org_id)
        if branch_user_ids is not None:
            query_filters.append(Lead.owner_id.in_(branch_user_ids))
        else:
            query_filters.append(Lead.owner_id == current_user.id)

        # Scope to leads created within the dashboard date range for meaningful metrics
        query_filters.append(Lead.created_at >= thirty_days_ago)

        lead_metrics_query = db.query(
            func.count(Lead.id).label('total_leads'),
            func.count(case((Lead.created_at >= today_start, 1))).label('new_today'),
            func.count(case((
                (Lead.ai_score >= 80) &
                (Lead.stage.in_([LeadStage.NEW, LeadStage.ATTEMPTED_CONTACT])), 1
            ))).label('hot_leads'),
            func.count(case((
                (Lead.ai_score >= 75) &
                (Lead.stage == LeadStage.ATTEMPTED_CONTACT), 1
            ))).label('high_intent')
        ).filter(*query_filters).first()

        total_leads = lead_metrics_query.total_leads or 1
        new_today = lead_metrics_query.new_today or 0
        hot_leads = lead_metrics_query.hot_leads or 0
        high_intent_leads = lead_metrics_query.high_intent or 0

        # Get applications count (already have it from earlier, but need to query separately)
        query_filters = []
        if org_id:
            query_filters.append(Loan.organization_id == org_id)
        if branch_user_ids is not None:
            query_filters.append(Loan.loan_officer_id.in_(branch_user_ids))
        else:
            query_filters.append(Loan.loan_officer_id == current_user.id)

        applications = db.query(func.count(Loan.id)).filter(*query_filters).scalar() or 0

        conversion_rate = int((applications / total_leads * 100)) if total_leads > 0 else 0

        # Calculate average contact time from lead data (time from creation to first contact attempt)
        # Uses EXTRACT to get hours between lead creation and first contact attempt
        query_filters = [
            Lead.first_contact_attempt_date.isnot(None),
            Lead.created_at.isnot(None)
        ]
        if org_id:
            query_filters.append(Lead.organization_id == org_id)
        if branch_user_ids is not None:
            query_filters.append(Lead.owner_id.in_(branch_user_ids))
        else:
            query_filters.append(Lead.owner_id == current_user.id)

        avg_contact_time_result = db.query(
            func.avg(
                func.extract('epoch', Lead.first_contact_attempt_date - Lead.created_at) / 3600
            ).label('avg_hours')
        ).filter(*query_filters).scalar()

        # Default to 1.2 hours if no data, otherwise round to 1 decimal
        avg_contact_time = round(float(avg_contact_time_result), 1) if avg_contact_time_result else 1.2
    except Exception as lead_metrics_err:
        logger.warning(f"Dashboard: Error getting lead metrics: {lead_metrics_err}")
        total_leads = 1
        new_today = hot_leads = high_intent_leads = applications = conversion_rate = 0
        avg_contact_time = 1.2

    # Generate AI alerts
    alerts = []
    if uncontacted_alerts > 0:
        alerts.append(f"{uncontacted_alerts} leads haven't been contacted in 24 hours.")

    if high_intent_leads > 0:
        alerts.append(f"{high_intent_leads} leads showed high buying intent.")

    lead_metrics = {
        "new_today": new_today,
        "avg_contact_time": avg_contact_time,
        "conversion_rate": conversion_rate,
        "hot_leads": hot_leads,
        "alerts": alerts
    }

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
    # TEAM STATS (if applicable)
    # ============================================================================

    team_stats = {
        "has_team": False,
        "avg_workload": 0,
        "backlog": 0,
        "sla_missed": 0,
        "insights": []
    }

    # ============================================================================
    # MESSAGES (placeholder for now)
    # ============================================================================

    messages = []

    # ============================================================================
    # EFFICIENCY METRICS
    # ============================================================================

    # Get total loan count for this user (to determine if they have any data)
    try:
        query_filters = []
        if org_id:
            query_filters.append(Loan.organization_id == org_id)
        if branch_user_ids is not None:
            query_filters.append(Loan.loan_officer_id.in_(branch_user_ids))
        else:
            query_filters.append(Loan.loan_officer_id == current_user.id)

        total_loan_count = db.query(Loan).filter(*query_filters).count()
    except Exception as e:
        logger.error(f"Error in get_dashboard (total_loan_count): {e}")
        total_loan_count = 0

    # Calculate average time to close from funded loans
    # Note: thirty_days_ago now comes from date range params or defaults to 30 days
    try:
        query_filters = [
            Loan.stage == LoanStage.FUNDED,
            Loan.funded_date >= thirty_days_ago
        ]
        if org_id:
            query_filters.append(Loan.organization_id == org_id)
        if branch_user_ids is not None:
            query_filters.append(Loan.loan_officer_id.in_(branch_user_ids))
        else:
            query_filters.append(Loan.loan_officer_id == current_user.id)

        funded_loans_recent = db.query(Loan).filter(*query_filters).all()
    except Exception as e:
        logger.error(f"Error in get_dashboard (funded_loans_recent): {e}")
        funded_loans_recent = []

    # Calculate avg time to close (use application_date for accuracy, fallback to created_at)
    time_to_close_list = []
    for loan in funded_loans_recent:
        if loan.funded_date:
            start_date = loan.application_date or loan.created_at
            if start_date:
                # Handle both datetime and date types
                funded_date = loan.funded_date.date() if hasattr(loan.funded_date, 'date') else loan.funded_date
                start_as_date = start_date.date() if hasattr(start_date, 'date') else start_date
                days = (funded_date - start_as_date).days
                if days > 0:
                    time_to_close_list.append(days)

    avg_time_to_close = sum(time_to_close_list) / len(time_to_close_list) if time_to_close_list else 0

    # Calculate pull-through rate using 90-day cohort:
    # Of loans created 90+ days ago, what % have funded?
    # This avoids comparing new loans that haven't had time to close.
    try:
        ninety_days_ago = today - timedelta(days=90)
        query_filters = [Loan.created_at <= ninety_days_ago]
        if org_id:
            query_filters.append(Loan.organization_id == org_id)
        if branch_user_ids is not None:
            query_filters.append(Loan.loan_officer_id.in_(branch_user_ids))
        else:
            query_filters.append(Loan.loan_officer_id == current_user.id)

        cohort_counts = db.query(
            func.count(Loan.id).label('total'),
            func.count(case((Loan.stage == LoanStage.FUNDED, 1))).label('funded')
        ).filter(*query_filters).first()

        cohort_total = cohort_counts.total or 0
        cohort_funded = cohort_counts.funded or 0
    except Exception as e:
        logger.error(f"Error in get_dashboard (pull_through_cohort): {e}")
        cohort_total = 0
        cohort_funded = 0

    pull_through_rate = int((cohort_funded / cohort_total * 100)) if cohort_total > 0 else 0

    # Count loans falling behind (in stage > 14 days)
    try:
        query_filters = [
            Loan.stage.in_([LoanStage.PROCESSING, LoanStage.UW_RECEIVED]),
            Loan.days_in_stage > 14
        ]
        if org_id:
            query_filters.append(Loan.organization_id == org_id)
        if branch_user_ids is not None:
            query_filters.append(Loan.loan_officer_id.in_(branch_user_ids))
        else:
            query_filters.append(Loan.loan_officer_id == current_user.id)

        loans_behind = db.query(func.count(Loan.id)).filter(*query_filters).scalar() or 0
    except Exception as e:
        logger.error(f"Error in get_dashboard (loans_behind): {e}")
        loans_behind = 0

    # Calculate automation rate from AI agent actions
    try:
        query_filters = [Task.created_at >= thirty_days_ago]
        if org_id:
            query_filters.append(Task.organization_id == org_id)
        if branch_user_ids is not None:
            query_filters.append(Task.owner_id.in_(branch_user_ids))
        else:
            query_filters.append(Task.owner_id == current_user.id)

        total_tasks = db.query(func.count(Task.id)).filter(*query_filters).scalar() or 1
    except Exception as e:
        logger.error(f"Error in get_dashboard (total_tasks): {e}")
        total_tasks = 1

    try:
        query_filters = [AIColleagueAction.created_at >= thirty_days_ago]
        if org_id:
            query_filters.append(AIColleagueAction.organization_id == org_id)
        if branch_user_ids is not None:
            query_filters.append(AIColleagueAction.user_id.in_(branch_user_ids))
        else:
            query_filters.append(AIColleagueAction.user_id == current_user.id)

        ai_tasks_count = db.query(func.count(AIColleagueAction.id)).filter(*query_filters).scalar() or 0
    except Exception as e:
        logger.error(f"Error in get_dashboard (ai_tasks_count): {e}")
        ai_tasks_count = 0

    automation_rate = int((ai_tasks_count / (total_tasks + ai_tasks_count) * 100)) if (total_tasks + ai_tasks_count) > 0 else 0

    # Customer satisfaction: requires real NPS/feedback data (not fabricated)
    customer_satisfaction = None

    # Overall efficiency score (weighted average)
    # When avg_time_to_close is 0 (no data), treat the time component as neutral (50)
    time_score = (100 - min(avg_time_to_close, 100)) if avg_time_to_close > 0 else 50
    overall_score = int((
        pull_through_rate * 0.3 +
        time_score * 0.3 +
        (100 - min(loans_behind * 5, 100)) * 0.2 +
        automation_rate * 0.2
    ))

    # Calculate trend values from historical data
    try:
        trends = calculate_efficiency_trends(db, current_user.id, org_id=org_id, branch_user_ids=branch_user_ids)
    except Exception as e:
        logger.error(f"Error in get_dashboard (efficiency_trends): {e}")
        trends = {"overall_trend": "stable", "time_to_close_change": 0, "pull_through_change": 0, "loans_behind_change": 0, "automation_change": 0}

    # Build efficiency dict with safe helper function calls
    try:
        stage_perf = calculate_stage_performance(db, current_user.id, thirty_days_ago, org_id=org_id, branch_user_ids=branch_user_ids) if total_loan_count > 0 else []
    except Exception as e:
        logger.error(f"Error in get_dashboard (stage_performance): {e}")
        stage_perf = []

    try:
        team_perf = calculate_team_performance(db, current_user.id, thirty_days_ago, org_id=org_id, branch_user_ids=branch_user_ids) if total_loan_count > 0 else []
    except Exception as e:
        logger.error(f"Error in get_dashboard (team_performance): {e}")
        team_perf = []

    try:
        bottlenecks = calculate_bottlenecks(db, current_user.id, org_id=org_id, branch_user_ids=branch_user_ids)
    except Exception as e:
        logger.error(f"Error in get_dashboard (bottlenecks): {e}")
        bottlenecks = []

    efficiency = {
        "overallScore": overall_score,
        "trend": trends["overall_trend"],

        # Key Metrics with real trend values
        "avgTimeToClose": round(avg_time_to_close, 1),
        "avgTimeToCloseChange": trends["time_to_close_change"],
        "pullThroughRate": pull_through_rate,
        "pullThroughRateChange": trends["pull_through_change"],
        "loansFallingBehind": loans_behind,
        "loansFallingBehindChange": trends["loans_behind_change"],
        "automationRate": automation_rate,
        "automationRateChange": trends["automation_change"],
        "customerSatisfaction": customer_satisfaction,
        "customerSatisfactionChange": 0,  # Would need historical satisfaction tracking

        # Stage Performance - calculated from real loan/lead data
        "stages": stage_perf,

        # Team Performance - calculated from real user metrics
        "team": team_perf,

        # Bottlenecks - dynamically calculated from real loan issues
        "bottleneckCount": len(bottlenecks),
        "bottlenecks": bottlenecks
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
        "loan_issues": [],
        "ai_tasks": {"pending": [], "waiting": []},
        "referral_stats": referral_stats,
        "team_stats": team_stats,
        "messages": messages,
        "efficiency": efficiency
    }

    # Cache for blazing fast retrieval on subsequent requests
    set_cached(cache_key, result)
    return result
