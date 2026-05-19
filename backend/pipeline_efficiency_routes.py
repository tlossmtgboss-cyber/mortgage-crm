"""
Pipeline Efficiency Routes - Real-time pipeline analytics from actual database data
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import func, case, and_, or_, extract
from datetime import datetime, timedelta, timezone
from typing import Optional
from pydantic import BaseModel
from enum import Enum

router = APIRouter(prefix="/api/v1/pipeline", tags=["Pipeline Efficiency"])

# Dependencies will be set from main.py
_get_db = None
_get_current_user = None
_models = None

def set_dependencies(get_db_func, get_current_user_func, models_dict=None):
    global _get_db, _get_current_user, _models
    _get_db = get_db_func
    _get_current_user = get_current_user_func
    _models = models_dict

def get_db():
    if _get_db is None:
        raise RuntimeError("Dependencies not set")
    yield from _get_db()

from auth.dependencies import get_current_user  # dedup: was local wrapper
class TimeRange(str, Enum):
    SEVEN_DAYS = "7days"
    THIRTY_DAYS = "30days"
    NINETY_DAYS = "90days"
    YEAR = "year"


# Roles that can see organization-wide data
ORG_WIDE_ROLES = ['admin', 'site_admin', 'leadership', 'management', 'company_admin', 'branch_manager']


def can_view_org_data(user) -> bool:
    """Check if user can view organization-wide pipeline data"""
    role = getattr(user, 'permission_role', None) or getattr(user, 'role', '')
    return role.lower() in [r.lower() for r in ORG_WIDE_ROLES]


def get_date_filter(time_range: TimeRange):
    """Get the start date for filtering based on time range"""
    now = datetime.now(timezone.utc)
    if time_range == TimeRange.SEVEN_DAYS:
        return now - timedelta(days=7)
    elif time_range == TimeRange.THIRTY_DAYS:
        return now - timedelta(days=30)
    elif time_range == TimeRange.NINETY_DAYS:
        return now - timedelta(days=90)
    else:  # YEAR
        return now - timedelta(days=365)


@router.get("/efficiency")
async def get_pipeline_efficiency(
    time_range: TimeRange = TimeRange.THIRTY_DAYS,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get overall pipeline efficiency metrics from real data"""
    import traceback
    import logging
    logger = logging.getLogger(__name__)

    try:
        # Use models from dependency injection to avoid circular imports
        if _models is None:
            raise RuntimeError("Models not configured - call set_dependencies with models_dict")

        Lead = _models.get('Lead')
        Loan = _models.get('Loan')
        LeadStage = _models.get('LeadStage')
        LoanStage = _models.get('LoanStage')

        if not all([Lead, Loan, LeadStage, LoanStage]):
            raise RuntimeError(f"Missing required models. Available: {list(_models.keys())}")

        start_date = get_date_filter(time_range)
        now = datetime.now(timezone.utc)

        # Determine if user should see org-wide data or just their own
        view_org_wide = can_view_org_data(current_user)
        org_id = getattr(current_user, 'organization_id', None)

        # Build base filters
        if view_org_wide and org_id:
            # Admin/management sees entire organization
            lead_filter = [Lead.created_at >= start_date, Lead.organization_id == org_id]
            loan_filter = [Loan.created_at >= start_date, Loan.organization_id == org_id]
            loan_base_filter = [Loan.organization_id == org_id]
        else:
            # Regular user sees only their own data
            lead_filter = [Lead.created_at >= start_date, Lead.owner_id == current_user.id]
            loan_filter = [Loan.created_at >= start_date, Loan.loan_officer_id == current_user.id]
            loan_base_filter = [Loan.loan_officer_id == current_user.id]

        # Get total leads in period
        total_leads = db.query(func.count(Lead.id)).filter(*lead_filter).scalar() or 0

        # Get total loans in period
        total_loans = db.query(func.count(Loan.id)).filter(*loan_filter).scalar() or 0

        # Calculate conversion rate (leads that became loans)
        converted_leads = db.query(func.count(Lead.id)).filter(
            *lead_filter,
            Lead.stage == LeadStage.CONVERTED
        ).scalar() or 0

        pull_through_rate = round((converted_leads / total_leads * 100), 1) if total_leads > 0 else 0

        # Calculate average time to close (for funded loans)
        funded_loan_filter = loan_base_filter + [
            Loan.funded_date >= start_date,
            Loan.funded_date.isnot(None),
            Loan.created_at.isnot(None)
        ]
        funded_loans = db.query(Loan).filter(*funded_loan_filter).all()

        if funded_loans:
            total_days = sum(
                (loan.funded_date - loan.created_at).days
                for loan in funded_loans
                if loan.funded_date and loan.created_at
            )
            avg_time_to_close = round(total_days / len(funded_loans), 1) if funded_loans else 0
        else:
            avg_time_to_close = 0

        # Get loans falling behind (in processing/underwriting for more than 14 days)
        falling_behind_stages = [LoanStage.PROCESSING, LoanStage.SUBMITTED, LoanStage.UNDERWRITING]
        # Also check for string versions in case enum isn't matching
        falling_behind_stage_values = [s.value if hasattr(s, 'value') else str(s) for s in falling_behind_stages]
        fourteen_days_ago = now - timedelta(days=14)

        loans_falling_behind = db.query(func.count(Loan.id)).filter(
            *loan_base_filter,
            or_(Loan.stage.in_(falling_behind_stages), Loan.stage.in_(falling_behind_stage_values)),
            Loan.created_at < fourteen_days_ago
        ).scalar() or 0

        # Calculate overall efficiency score (weighted average)
        # Higher pull-through = better, Lower time to close = better, fewer falling behind = better
        efficiency_components = []
        if total_leads > 0:
            efficiency_components.append(min(pull_through_rate, 100))
        if avg_time_to_close > 0:
            # Benchmark: 45 days is average, lower is better
            time_efficiency = max(0, 100 - ((avg_time_to_close - 30) * 2))
            efficiency_components.append(min(time_efficiency, 100))
        if total_loans > 0:
            behind_rate = (loans_falling_behind / total_loans) * 100 if total_loans > 0 else 0
            behind_efficiency = max(0, 100 - (behind_rate * 5))
            efficiency_components.append(behind_efficiency)

        overall_score = round(sum(efficiency_components) / len(efficiency_components), 0) if efficiency_components else 0

        return {
            "overallScore": overall_score,
            "trend": 0,  # Would need historical data to calculate
            "lastUpdated": now.isoformat(),
            "hasData": total_leads > 0 or total_loans > 0,
            "keyMetrics": {
                "avgTimeToClose": avg_time_to_close,
                "avgTimeToCloseChange": 0,
                "pullThroughRate": pull_through_rate,
                "pullThroughRateChange": 0,
                "loansFallingBehind": loans_falling_behind,
                "loansFallingBehindChange": 0,
                "automationRate": 0,  # Would need task tracking to calculate
                "automationRateChange": 0,
                "customerSatisfaction": 0,  # Would need feedback system
                "customerSatisfactionChange": 0
            },
            "summary": {
                "totalLeads": total_leads,
                "totalLoans": total_loans,
                "convertedLeads": converted_leads,
                "fundedLoans": len(funded_loans) if funded_loans else 0
            }
        }
    except Exception as e:
        logger.error(f"Pipeline efficiency error: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Pipeline efficiency error")


@router.get("/stages")
async def get_stage_metrics(
    time_range: TimeRange = TimeRange.THIRTY_DAYS,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get stage-by-stage pipeline metrics"""
    if _models is None:
        raise HTTPException(status_code=500, detail="Models not configured")

    Lead = _models.get('Lead')
    Loan = _models.get('Loan')
    LeadStage = _models.get('LeadStage')
    LoanStage = _models.get('LoanStage')

    start_date = get_date_filter(time_range)
    now = datetime.now(timezone.utc)

    # Determine if user should see org-wide data or just their own
    view_org_wide = can_view_org_data(current_user)
    org_id = getattr(current_user, 'organization_id', None)

    # Define stages with their mappings
    lead_stages = [
        {"name": "New Lead", "stage": LeadStage.NEW, "type": "lead"},
        {"name": "Contacted", "stage": LeadStage.CONTACTED, "type": "lead"},
        {"name": "Qualified", "stage": LeadStage.QUALIFIED, "type": "lead"},
        {"name": "Application", "stage": LeadStage.APPLICATION, "type": "lead"},
        {"name": "Pre-Approved", "stage": LeadStage.PREAPPROVED, "type": "lead"},
    ]

    loan_stages = [
        {"name": "Disclosed", "stage": LoanStage.DISCLOSED, "type": "loan"},
        {"name": "Processing", "stage": LoanStage.PROCESSING, "type": "loan"},
        {"name": "Submitted", "stage": LoanStage.SUBMITTED, "type": "loan"},
        {"name": "Underwriting", "stage": LoanStage.UNDERWRITING, "type": "loan"},
        {"name": "Approved", "stage": LoanStage.APPROVED, "type": "loan"},
        {"name": "Clear to Close", "stage": LoanStage.CTC, "type": "loan"},
        {"name": "Docs Out", "stage": LoanStage.DOCS_OUT, "type": "loan"},
        {"name": "Funded", "stage": LoanStage.FUNDED, "type": "loan"},
    ]

    stage_metrics = []

    # Process lead stages
    for stage_info in lead_stages:
        # Build filter based on user role
        if view_org_wide and org_id:
            lead_base = [Lead.organization_id == org_id]
        else:
            lead_base = [Lead.owner_id == current_user.id]

        # Match both enum and string value for stage
        stage_value = stage_info["stage"].value if hasattr(stage_info["stage"], 'value') else str(stage_info["stage"])
        stage_match = or_(Lead.stage == stage_info["stage"], Lead.stage == stage_value)

        count = db.query(func.count(Lead.id)).filter(
            *lead_base, stage_match
        ).scalar() or 0

        # Calculate average days in stage
        leads_in_stage = db.query(Lead).filter(
            *lead_base, stage_match,
            Lead.stage_changed_at.isnot(None)
        ).all()

        if leads_in_stage:
            total_days = sum(
                (now - lead.stage_changed_at).days
                for lead in leads_in_stage
                if lead.stage_changed_at
            )
            avg_days = round(total_days / len(leads_in_stage), 1)
        else:
            avg_days = 0

        stage_metrics.append({
            "name": stage_info["name"],
            "type": stage_info["type"],
            "volume": count,
            "avgTime": f"{avg_days} days",
            "avgDays": avg_days,
            "efficiency": 100 if avg_days <= 3 else max(0, 100 - (avg_days - 3) * 10),
            "conversionRate": 0,  # Would need stage transition tracking
            "bottlenecks": 1 if avg_days > 7 else 0,
            "trend": 0
        })

    # Process loan stages
    for stage_info in loan_stages:
        # Build filter based on user role
        if view_org_wide and org_id:
            loan_base = [Loan.organization_id == org_id]
        else:
            loan_base = [Loan.loan_officer_id == current_user.id]

        # Match both enum and string value for stage
        stage_value = stage_info["stage"].value if hasattr(stage_info["stage"], 'value') else str(stage_info["stage"])
        stage_match = or_(Loan.stage == stage_info["stage"], Loan.stage == stage_value)

        count = db.query(func.count(Loan.id)).filter(
            *loan_base, stage_match
        ).scalar() or 0

        # For loans, use created_at as proxy for stage entry (simplified)
        avg_days = 0  # Would need stage history tracking for accurate calculation

        stage_metrics.append({
            "name": stage_info["name"],
            "type": stage_info["type"],
            "volume": count,
            "avgTime": f"{avg_days} days",
            "avgDays": avg_days,
            "efficiency": 80,  # Default efficiency
            "conversionRate": 0,
            "bottlenecks": 0,
            "trend": 0
        })

    # Check if there's any data
    has_data = any(s["volume"] > 0 for s in stage_metrics)

    return {
        "hasData": has_data,
        "stageMetrics": stage_metrics
    }


@router.get("/team")
async def get_team_metrics(
    time_range: TimeRange = TimeRange.THIRTY_DAYS,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get team performance metrics"""
    from sqlalchemy import text

    start_date = get_date_filter(time_range)
    team_metrics = []

    try:
        # Get team members - check if current user is a manager/admin
        # or get all users in the same organization
        team_query = db.execute(text("""
            SELECT
                u.id,
                u.full_name,
                u.email,
                u.role,
                COUNT(DISTINCT l.id) as lead_count,
                COUNT(DISTINCT CASE WHEN l.stage IN ('converted', 'closed_won') THEN l.id END) as converted_count,
                COUNT(DISTINCT lo.id) as loan_count,
                COUNT(DISTINCT CASE WHEN lo.status = 'funded' THEN lo.id END) as funded_count,
                COALESCE(SUM(CASE WHEN lo.status = 'funded' THEN lo.loan_amount ELSE 0 END), 0) as funded_volume
            FROM users u
            LEFT JOIN leads l ON l.assigned_to = u.id
                AND l.created_at >= :start_date
            LEFT JOIN loans lo ON lo.loan_officer_id = u.id
                AND lo.created_at >= :start_date
            WHERE u.is_active = 1
                AND (u.organization_id = :org_id OR :org_id IS NULL)
                AND u.role IN ('loan_officer', 'sales', 'admin')
            GROUP BY u.id, u.full_name, u.email, u.role
            HAVING COUNT(DISTINCT l.id) > 0 OR COUNT(DISTINCT lo.id) > 0
            ORDER BY funded_volume DESC
            LIMIT 20
        """), {
            "start_date": start_date.isoformat(),
            "org_id": getattr(current_user, 'organization_id', None)
        })

        for row in team_query:
            conversion_rate = 0
            if row[4] > 0:  # lead_count
                conversion_rate = round((row[5] / row[4]) * 100, 1)  # converted_count / lead_count

            team_metrics.append({
                "id": row[0],
                "name": row[1] or row[2].split("@")[0],
                "email": row[2],
                "role": (row[3] or "loan_officer").replace("_", " ").title(),
                "leads": row[4] or 0,
                "conversions": row[5] or 0,
                "conversionRate": conversion_rate,
                "loans": row[6] or 0,
                "funded": row[7] or 0,
                "volume": float(row[8] or 0),
                "volumeFormatted": f"${float(row[8] or 0):,.0f}"
            })

    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Team metrics query failed: {e}")
        # Return empty but valid response

    return {
        "hasData": len(team_metrics) > 0,
        "teamMetrics": team_metrics,
        "timeRange": time_range.value
    }


@router.get("/bottlenecks")
async def get_bottlenecks(
    time_range: TimeRange = TimeRange.THIRTY_DAYS,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get current pipeline bottlenecks"""
    if _models is None:
        raise HTTPException(status_code=500, detail="Models not configured")

    Lead = _models.get('Lead')
    Loan = _models.get('Loan')
    LeadStage = _models.get('LeadStage')
    LoanStage = _models.get('LoanStage')

    now = datetime.now(timezone.utc)
    bottlenecks = []

    # Determine if user should see org-wide data or just their own
    view_org_wide = can_view_org_data(current_user)
    org_id = getattr(current_user, 'organization_id', None)

    # Check for leads stuck in each stage too long
    stage_thresholds = {
        LeadStage.NEW: 2,
        LeadStage.CONTACTED: 5,
        LeadStage.QUALIFIED: 7,
        LeadStage.APPLICATION: 10,
    }

    for stage, threshold_days in stage_thresholds.items():
        threshold_date = now - timedelta(days=threshold_days)

        # Build filter based on user role
        if view_org_wide and org_id:
            lead_base = [Lead.organization_id == org_id]
        else:
            lead_base = [Lead.owner_id == current_user.id]

        # Match both enum and string value for stage
        stage_value = stage.value if hasattr(stage, 'value') else str(stage)
        stage_match = or_(Lead.stage == stage, Lead.stage == stage_value)

        stuck_leads = db.query(Lead).filter(
            *lead_base,
            stage_match,
            or_(
                Lead.stage_changed_at < threshold_date,
                and_(Lead.stage_changed_at.is_(None), Lead.created_at < threshold_date)
            )
        ).all()

        if stuck_leads:
            avg_days = sum(
                (now - (lead.stage_changed_at or lead.created_at)).days
                for lead in stuck_leads
            ) / len(stuck_leads)

            bottlenecks.append({
                "id": len(bottlenecks) + 1,
                "stage": stage_value,
                "issue": f"Leads stuck in {stage_value}",
                "affectedCount": len(stuck_leads),
                "avgDelay": f"{round(avg_days, 1)} days",
                "severity": "high" if avg_days > threshold_days * 2 else "medium",
                "type": "lead"
            })

    # Check for loans in processing too long
    loan_thresholds = {
        LoanStage.PROCESSING: 14,
        LoanStage.UNDERWRITING: 10,
        LoanStage.SUBMITTED: 7,
    }

    for stage, threshold_days in loan_thresholds.items():
        threshold_date = now - timedelta(days=threshold_days)

        # Build filter based on user role
        if view_org_wide and org_id:
            loan_base = [Loan.organization_id == org_id]
        else:
            loan_base = [Loan.loan_officer_id == current_user.id]

        # Match both enum and string value for stage
        stage_value = stage.value if hasattr(stage, 'value') else str(stage)
        stage_match = or_(Loan.stage == stage, Loan.stage == stage_value)

        stuck_loans = db.query(func.count(Loan.id)).filter(
            *loan_base,
            stage_match,
            Loan.created_at < threshold_date
        ).scalar() or 0

        if stuck_loans > 0:
            bottlenecks.append({
                "id": len(bottlenecks) + 1,
                "stage": stage_value,
                "issue": f"Loans delayed in {stage_value}",
                "affectedCount": stuck_loans,
                "avgDelay": f">{threshold_days} days",
                "severity": "high" if stuck_loans > 3 else "medium",
                "type": "loan"
            })

    return {
        "hasData": len(bottlenecks) > 0,
        "bottlenecks": bottlenecks
    }


@router.get("/trends")
async def get_trends(
    weeks: int = 12,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get efficiency trends over time"""
    if _models is None:
        raise HTTPException(status_code=500, detail="Models not configured")

    Lead = _models.get('Lead')
    Loan = _models.get('Loan')

    now = datetime.now(timezone.utc)
    trends = []

    # Determine if user should see org-wide data or just their own
    view_org_wide = can_view_org_data(current_user)
    org_id = getattr(current_user, 'organization_id', None)

    for i in range(weeks - 1, -1, -1):
        week_end = now - timedelta(weeks=i)
        week_start = week_end - timedelta(weeks=1)

        # Build filters based on user role
        if view_org_wide and org_id:
            lead_filter = [Lead.organization_id == org_id, Lead.created_at >= week_start, Lead.created_at < week_end]
            loan_filter = [Loan.organization_id == org_id, Loan.created_at >= week_start, Loan.created_at < week_end]
        else:
            lead_filter = [Lead.owner_id == current_user.id, Lead.created_at >= week_start, Lead.created_at < week_end]
            loan_filter = [Loan.loan_officer_id == current_user.id, Loan.created_at >= week_start, Loan.created_at < week_end]

        # Count leads created in this week
        lead_count = db.query(func.count(Lead.id)).filter(*lead_filter).scalar() or 0

        # Count loans created in this week
        loan_count = db.query(func.count(Loan.id)).filter(*loan_filter).scalar() or 0

        total_volume = lead_count + loan_count
        # Simple efficiency score based on volume (would be more sophisticated in production)
        score = min(100, 50 + total_volume * 5) if total_volume > 0 else 0

        trends.append({
            "week": f"Week {weeks - i}",
            "score": score,
            "volume": total_volume,
            "leads": lead_count,
            "loans": loan_count
        })

    has_data = any(t["volume"] > 0 for t in trends)

    return {
        "hasData": has_data,
        "trends": trends
    }
