"""
Usage Intelligence API Routes

Owner-only endpoints for viewing usage costs, projections, and pricing recommendations.
Provides data for the Usage Intelligence dashboard.

All routes require owner/admin authentication.
"""

import os
import logging
from datetime import datetime, date, timedelta, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from sqlalchemy import text

# OAuth2 scheme for token extraction
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Database and user dependencies - injected from main app
_get_db = None
_get_current_user = None


from db import get_db


def set_dependencies(get_db_func, get_current_user_func):
    """Set the database and user dependencies from main app."""
    global _get_db, _get_current_user
    _get_db = get_db_func
    _get_current_user = get_current_user_func


from auth.dependencies import get_current_user  # dedup: was local wrapper
async def require_owner(current_user = Depends(get_current_user)):
    """Require owner/admin role for access."""
    if current_user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Check both role and permission_role fields
    role = (getattr(current_user, 'role', '') or '').lower()
    permission_role = (getattr(current_user, 'permission_role', '') or '').lower()
    is_admin = getattr(current_user, 'is_admin', False)

    allowed_roles = ["admin", "owner", "leadership", "site_admin", "management"]

    if role in allowed_roles or permission_role in allowed_roles or is_admin:
        return current_user

    raise HTTPException(status_code=403, detail="Owner access required")

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/usage-intelligence",
    tags=["Usage Intelligence"]
)


# =============================================================================
# DEPENDENCIES
# =============================================================================

def _require_org_id(current_user) -> int:
    """Extract and validate organization_id from current_user. Raises 403 if missing."""
    org_id = getattr(current_user, 'organization_id', None)
    if not org_id:
        raise HTTPException(status_code=403, detail="Organization context required")
    return org_id


def get_projection_service(db: Session, organization_id: int = None):
    """Get the projection service instance."""
    if not organization_id:
        raise HTTPException(status_code=403, detail="Organization context required")
    from services.usage_projection_service import UsageProjectionService
    return UsageProjectionService(db, organization_id=organization_id)


# =============================================================================
# DASHBOARD OVERVIEW
# =============================================================================

@router.get("/dashboard")
async def get_dashboard_overview(
    current_user: dict = Depends(require_owner),
    db: Session = Depends(get_db)
):
    """
    Get overview data for the usage intelligence dashboard.
    Includes KPIs, recent trends, and alerts.
    """
    today = date.today()
    yesterday = today - timedelta(days=1)
    month_start = today.replace(day=1)
    prev_month_start = (month_start - timedelta(days=1)).replace(day=1)
    prev_month_end = month_start - timedelta(days=1)

    # Get MTD totals
    mtd_data = db.execute(text("""
        SELECT
            COALESCE(SUM(total_cost), 0) as total_cost,
            COALESCE(SUM(ai_tokens_cost), 0) as ai_cost,
            COALESCE(SUM(communications_cost), 0) as comm_cost,
            COALESCE(SUM(storage_cost), 0) as storage_cost,
            COUNT(DISTINCT snapshot_date) as days_with_data,
            MAX(user_count) as user_count
        FROM org_usage_snapshots
        WHERE organization_id = :org_id
        AND snapshot_date >= :month_start
        AND snapshot_date < :today
    """), {
        "org_id": _require_org_id(current_user),
        "month_start": month_start,
        "today": today
    }).fetchone()

    # Get previous month totals for comparison
    prev_month_data = db.execute(text("""
        SELECT
            COALESCE(SUM(total_cost), 0) as total_cost,
            COUNT(DISTINCT snapshot_date) as days_with_data
        FROM org_usage_snapshots
        WHERE organization_id = :org_id
        AND snapshot_date >= :prev_start
        AND snapshot_date <= :prev_end
    """), {
        "org_id": _require_org_id(current_user),
        "prev_start": prev_month_start,
        "prev_end": prev_month_end
    }).fetchone()

    # Calculate daily average and project full month
    mtd_cost = float(mtd_data[0]) if mtd_data[0] else 0
    days_elapsed = int(mtd_data[4]) if mtd_data[4] else (yesterday - month_start).days + 1
    days_in_month = (month_start.replace(month=month_start.month % 12 + 1, day=1) - timedelta(days=1)).day if month_start.month < 12 else 31

    avg_daily = mtd_cost / max(days_elapsed, 1)
    projected_monthly = avg_daily * days_in_month

    # Month-over-month change
    prev_cost = float(prev_month_data[0]) if prev_month_data[0] else 0
    mom_change_pct = ((projected_monthly - prev_cost) / prev_cost * 100) if prev_cost > 0 else 0

    # Get recent alerts
    alerts = db.execute(text("""
        SELECT
            id, alert_type, severity, title, message, status, created_at
        FROM usage_alerts
        WHERE organization_id = :org_id
        AND status = 'active'
        ORDER BY created_at DESC
        LIMIT 5
    """), {
        "org_id": _require_org_id(current_user)
    }).fetchall()

    # Get 30-day projection
    org_id = _require_org_id(current_user)
    projection_service = get_projection_service(db, organization_id=org_id)
    projection = projection_service.generate_projections(
        scope_type="organization",
        period_days=30
    )

    return {
        "kpis": {
            "mtd_cost": round(mtd_cost, 2),
            "projected_monthly": round(projected_monthly, 2),
            "avg_daily_cost": round(avg_daily, 2),
            "prev_month_cost": round(prev_cost, 2),
            "mom_change_pct": round(mom_change_pct, 1),
            "active_users": mtd_data[5] if mtd_data[5] else 0,
            "days_elapsed": days_elapsed
        },
        "cost_breakdown": {
            "ai_tokens": round(float(mtd_data[1]) if mtd_data[1] else 0, 2),
            "communications": round(float(mtd_data[2]) if mtd_data[2] else 0, 2),
            "storage": round(float(mtd_data[3]) if mtd_data[3] else 0, 2)
        },
        "projection_30d": {
            "projected_cost": projection["projected_cost"],
            "confidence_low": projection["confidence_interval_low"],
            "confidence_high": projection["confidence_interval_high"],
            "trend_direction": projection["trend_direction"],
            "trend_percentage": projection["trend_percentage"]
        },
        "alerts": [
            {
                "id": str(a[0]),
                "type": a[1],
                "severity": a[2],
                "title": a[3],
                "message": a[4],
                "status": a[5],
                "created_at": a[6].isoformat() if a[6] else None
            }
            for a in alerts
        ]
    }


# =============================================================================
# USER COSTS
# =============================================================================

@router.get("/users")
async def get_user_costs(
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(50, ge=1, le=100),
    current_user: dict = Depends(require_owner),
    db: Session = Depends(get_db)
):
    """
    Get cost breakdown by user for the specified period.
    """
    org_id = _require_org_id(current_user)
    projection_service = get_projection_service(db, organization_id=org_id)
    ranking = projection_service.get_user_cost_ranking(
        period_days=days,
        limit=limit
    )

    # Get total cost for percentage calculation
    total_cost = sum(u["total_cost"] for u in ranking)

    for user in ranking:
        user["pct_of_total"] = round((user["total_cost"] / total_cost * 100) if total_cost > 0 else 0, 1)

    return {
        "period_days": days,
        "total_users": len(ranking),
        "total_cost": round(total_cost, 2),
        "users": ranking
    }


@router.get("/users/{user_id}")
async def get_user_cost_detail(
    user_id: int,
    days: int = Query(30, ge=1, le=365),
    current_user: dict = Depends(require_owner),
    db: Session = Depends(get_db)
):
    """
    Get detailed cost breakdown for a specific user.
    """
    end_date = date.today() - timedelta(days=1)
    start_date = end_date - timedelta(days=days)

    # Get user info
    user_info = db.execute(text("""
        SELECT u.id, COALESCE(es.full_name, u.email) AS name, u.email, u.role
        FROM users u LEFT JOIN email_signatures es ON es.user_id = u.id
        WHERE u.id = :user_id
    """), {"user_id": user_id}).fetchone()

    if not user_info:
        raise HTTPException(status_code=404, detail="User not found")

    # Get daily breakdown
    daily_costs = db.execute(text("""
        SELECT
            snapshot_date,
            total_cost,
            ai_tokens_cost,
            sms_cost,
            voice_cost,
            email_cost,
            storage_cost,
            ai_tokens_input,
            ai_tokens_output,
            ai_request_count
        FROM user_usage_snapshots
        WHERE organization_id = :org_id
        AND user_id = :user_id
        AND snapshot_date BETWEEN :start_date AND :end_date
        ORDER BY snapshot_date DESC
    """), {
        "org_id": _require_org_id(current_user),
        "user_id": user_id,
        "start_date": start_date,
        "end_date": end_date
    }).fetchall()

    # Get model breakdown
    model_costs = db.execute(text("""
        SELECT
            model,
            SUM(input_tokens) as input_tokens,
            SUM(output_tokens) as output_tokens,
            SUM(total_cost) as total_cost,
            COUNT(*) as request_count
        FROM ai_token_usage_log
        WHERE organization_id = :org_id
        AND user_id = :user_id
        AND timestamp >= :start_date
        GROUP BY model
        ORDER BY total_cost DESC
    """), {
        "org_id": _require_org_id(current_user),
        "user_id": user_id,
        "start_date": start_date
    }).fetchall()

    # Get feature breakdown
    feature_costs = db.execute(text("""
        SELECT
            COALESCE(feature, 'unknown') as feature,
            SUM(total_cost) as total_cost,
            COUNT(*) as request_count
        FROM ai_token_usage_log
        WHERE organization_id = :org_id
        AND user_id = :user_id
        AND timestamp >= :start_date
        GROUP BY feature
        ORDER BY total_cost DESC
    """), {
        "org_id": _require_org_id(current_user),
        "user_id": user_id,
        "start_date": start_date
    }).fetchall()

    total_cost = sum(float(d[1]) for d in daily_costs)

    return {
        "user": {
            "id": user_info[0],
            "name": user_info[1],
            "email": user_info[2],
            "role": user_info[3]
        },
        "period_days": days,
        "total_cost": round(total_cost, 2),
        "avg_daily_cost": round(total_cost / max(days, 1), 2),
        "daily_breakdown": [
            {
                "date": str(d[0]),
                "total_cost": round(float(d[1]), 2),
                "ai_cost": round(float(d[2]), 2),
                "sms_cost": round(float(d[3]), 2),
                "voice_cost": round(float(d[4]), 2),
                "email_cost": round(float(d[5]), 2),
                "storage_cost": round(float(d[6]), 2),
                "ai_tokens": int(d[7]) + int(d[8]),
                "ai_requests": int(d[9])
            }
            for d in daily_costs
        ],
        "by_model": [
            {
                "model": m[0],
                "input_tokens": int(m[1]),
                "output_tokens": int(m[2]),
                "total_cost": round(float(m[3]), 2),
                "request_count": int(m[4])
            }
            for m in model_costs
        ],
        "by_feature": [
            {
                "feature": f[0],
                "total_cost": round(float(f[1]), 2),
                "request_count": int(f[2])
            }
            for f in feature_costs
        ]
    }


# =============================================================================
# TEAM COSTS
# =============================================================================

@router.get("/teams")
async def get_team_costs(
    days: int = Query(30, ge=1, le=365),
    current_user: dict = Depends(require_owner),
    db: Session = Depends(get_db)
):
    """
    Get cost breakdown by team for the specified period.
    """
    end_date = date.today() - timedelta(days=1)
    start_date = end_date - timedelta(days=days)

    teams = db.execute(text("""
        SELECT
            tus.team_id,
            t.name as team_name,
            COALESCE(SUM(tus.total_cost), 0) as total_cost,
            MAX(tus.user_count) as user_count,
            COALESCE(SUM(tus.ai_tokens_cost), 0) as ai_cost,
            COALESCE(SUM(tus.communications_cost), 0) as comm_cost,
            COALESCE(SUM(tus.storage_cost), 0) as storage_cost
        FROM team_usage_snapshots tus
        LEFT JOIN teams t ON t.id = tus.team_id
        WHERE tus.organization_id = :org_id
        AND tus.snapshot_date BETWEEN :start_date AND :end_date
        GROUP BY tus.team_id, t.name
        ORDER BY total_cost DESC
    """), {
        "org_id": _require_org_id(current_user),
        "start_date": start_date,
        "end_date": end_date
    }).fetchall()

    total_cost = sum(float(t[2]) for t in teams)

    return {
        "period_days": days,
        "total_teams": len(teams),
        "total_cost": round(total_cost, 2),
        "teams": [
            {
                "team_id": t[0],
                "team_name": t[1] or f"Team {t[0]}",
                "total_cost": round(float(t[2]), 2),
                "user_count": t[3] or 0,
                "cost_per_user": round(float(t[2]) / max(t[3] or 1, 1), 2),
                "ai_cost": round(float(t[4]), 2),
                "communications_cost": round(float(t[5]), 2),
                "storage_cost": round(float(t[6]), 2),
                "pct_of_total": round((float(t[2]) / total_cost * 100) if total_cost > 0 else 0, 1)
            }
            for t in teams
        ]
    }


# =============================================================================
# ORGANIZATION COSTS
# =============================================================================

@router.get("/organization")
async def get_organization_costs(
    days: int = Query(30, ge=1, le=365),
    current_user: dict = Depends(require_owner),
    db: Session = Depends(get_db)
):
    """
    Get organization-wide cost summary.
    """
    end_date = date.today() - timedelta(days=1)
    start_date = end_date - timedelta(days=days)

    data = db.execute(text("""
        SELECT
            COALESCE(SUM(total_cost), 0) as total_cost,
            COALESCE(SUM(ai_tokens_cost), 0) as ai_cost,
            COALESCE(SUM(communications_cost), 0) as comm_cost,
            COALESCE(SUM(storage_cost), 0) as storage_cost,
            COALESCE(SUM(infrastructure_cost), 0) as infra_cost,
            COALESCE(SUM(ai_tokens_input), 0) as total_input_tokens,
            COALESCE(SUM(ai_tokens_output), 0) as total_output_tokens,
            COALESCE(SUM(ai_request_count), 0) as total_requests,
            COALESCE(SUM(sms_segments), 0) as sms_segments,
            COALESCE(SUM(voice_minutes), 0) as voice_minutes,
            COALESCE(SUM(email_count), 0) as email_count,
            MAX(user_count) as user_count,
            MAX(team_count) as team_count
        FROM org_usage_snapshots
        WHERE organization_id = :org_id
        AND snapshot_date BETWEEN :start_date AND :end_date
    """), {
        "org_id": _require_org_id(current_user),
        "start_date": start_date,
        "end_date": end_date
    }).fetchone()

    total_cost = float(data[0]) if data[0] else 0

    return {
        "period_days": days,
        "period_start": str(start_date),
        "period_end": str(end_date),
        "totals": {
            "total_cost": round(total_cost, 2),
            "ai_tokens_cost": round(float(data[1]) if data[1] else 0, 2),
            "communications_cost": round(float(data[2]) if data[2] else 0, 2),
            "storage_cost": round(float(data[3]) if data[3] else 0, 2),
            "infrastructure_cost": round(float(data[4]) if data[4] else 0, 2)
        },
        "usage": {
            "total_input_tokens": int(data[5]) if data[5] else 0,
            "total_output_tokens": int(data[6]) if data[6] else 0,
            "total_ai_requests": int(data[7]) if data[7] else 0,
            "sms_segments": int(data[8]) if data[8] else 0,
            "voice_minutes": round(float(data[9]) if data[9] else 0, 1),
            "email_count": int(data[10]) if data[10] else 0
        },
        "stats": {
            "user_count": int(data[11]) if data[11] else 0,
            "team_count": int(data[12]) if data[12] else 0,
            "avg_daily_cost": round(total_cost / max(days, 1), 2),
            "avg_cost_per_user": round(total_cost / max(int(data[11]) if data[11] else 1, 1), 2)
        }
    }


@router.get("/organization/trend")
async def get_organization_cost_trend(
    days: int = Query(30, ge=1, le=365),
    current_user: dict = Depends(require_owner),
    db: Session = Depends(get_db)
):
    """
    Get daily cost trend for organization.
    """
    org_id = _require_org_id(current_user)
    projection_service = get_projection_service(db, organization_id=org_id)
    trend = projection_service.get_cost_trend(
        scope_type="organization",
        days=days
    )

    return {
        "period_days": days,
        "data": trend
    }


# =============================================================================
# PROJECTIONS
# =============================================================================

@router.get("/projections/{scope_type}")
async def get_projections(
    scope_type: str,
    scope_id: Optional[int] = None,
    period: int = Query(30, description="30, 60, or 90 days"),
    current_user: dict = Depends(require_owner),
    db: Session = Depends(get_db)
):
    """
    Get cost projections for specified scope.
    """
    if scope_type not in ["user", "team", "organization"]:
        raise HTTPException(status_code=400, detail="Invalid scope_type. Use 'user', 'team', or 'organization'")

    if scope_type in ["user", "team"] and not scope_id:
        raise HTTPException(status_code=400, detail=f"{scope_type}_id is required for {scope_type} scope")

    if period not in [30, 60, 90]:
        raise HTTPException(status_code=400, detail="Period must be 30, 60, or 90 days")

    org_id = _require_org_id(current_user)
    projection_service = get_projection_service(db, organization_id=org_id)
    projection = projection_service.generate_projections(
        scope_type=scope_type,
        scope_id=scope_id,
        period_days=period
    )

    return projection


# =============================================================================
# PRICING CALCULATOR
# =============================================================================

@router.get("/pricing-calculator")
async def get_pricing_recommendation(
    target_margin: float = Query(200, ge=50, le=500, description="Target margin percentage"),
    period_days: int = Query(30, ge=7, le=90),
    current_user: dict = Depends(require_owner),
    db: Session = Depends(get_db)
):
    """
    Calculate pricing recommendations based on actual costs.
    200% margin = Price is 3x cost (cost + 200% profit).
    """
    org_id = _require_org_id(current_user)
    projection_service = get_projection_service(db, organization_id=org_id)
    recommendation = projection_service.calculate_pricing_recommendation(
        target_margin_pct=target_margin,
        period_days=period_days
    )

    return recommendation


@router.post("/pricing-calculator/simulate")
async def simulate_pricing(
    base_price: float = Query(..., ge=0),
    per_user_price: float = Query(..., ge=0),
    current_user: dict = Depends(require_owner),
    db: Session = Depends(get_db)
):
    """
    Simulate margin with custom pricing.
    """
    end_date = date.today() - timedelta(days=1)
    start_date = end_date - timedelta(days=30)

    # Get actual costs
    data = db.execute(text("""
        SELECT
            COALESCE(SUM(total_cost), 0) as total_cost,
            MAX(user_count) as user_count
        FROM org_usage_snapshots
        WHERE organization_id = :org_id
        AND snapshot_date BETWEEN :start_date AND :end_date
    """), {
        "org_id": _require_org_id(current_user),
        "start_date": start_date,
        "end_date": end_date
    }).fetchone()

    total_cost = float(data[0]) if data[0] else 0
    user_count = int(data[1]) if data[1] else 1

    # Calculate revenue at proposed pricing
    proposed_revenue = base_price + (per_user_price * user_count)
    proposed_profit = proposed_revenue - total_cost
    proposed_margin = ((proposed_revenue - total_cost) / total_cost * 100) if total_cost > 0 else 0

    return {
        "proposed_pricing": {
            "base_price": base_price,
            "per_user_price": per_user_price
        },
        "actual_cost": round(total_cost, 2),
        "user_count": user_count,
        "proposed_revenue": round(proposed_revenue, 2),
        "proposed_profit": round(proposed_profit, 2),
        "proposed_margin_pct": round(proposed_margin, 1),
        "is_profitable": proposed_profit > 0,
        "meets_200_pct_target": proposed_margin >= 200
    }


# =============================================================================
# AI MODELS BREAKDOWN
# =============================================================================

@router.get("/ai-models")
async def get_ai_model_costs(
    days: int = Query(30, ge=1, le=365),
    current_user: dict = Depends(require_owner),
    db: Session = Depends(get_db)
):
    """
    Get cost breakdown by AI model.
    """
    end_date = date.today()
    start_date = end_date - timedelta(days=days)

    models = db.execute(text("""
        SELECT
            provider,
            model,
            SUM(input_tokens) as input_tokens,
            SUM(output_tokens) as output_tokens,
            SUM(total_cost) as total_cost,
            COUNT(*) as request_count,
            AVG(latency_ms) as avg_latency
        FROM ai_token_usage_log
        WHERE organization_id = :org_id
        AND timestamp >= :start_date
        GROUP BY provider, model
        ORDER BY total_cost DESC
    """), {
        "org_id": _require_org_id(current_user),
        "start_date": start_date
    }).fetchall()

    total_cost = sum(float(m[4]) for m in models)

    return {
        "period_days": days,
        "total_cost": round(total_cost, 2),
        "models": [
            {
                "provider": m[0],
                "model": m[1],
                "input_tokens": int(m[2]),
                "output_tokens": int(m[3]),
                "total_cost": round(float(m[4]), 2),
                "request_count": int(m[5]),
                "avg_latency_ms": round(float(m[6]) if m[6] else 0, 0),
                "pct_of_total": round((float(m[4]) / total_cost * 100) if total_cost > 0 else 0, 1),
                "cost_per_request": round(float(m[4]) / max(int(m[5]), 1), 4)
            }
            for m in models
        ]
    }


@router.get("/ai-models/pricing")
async def get_ai_model_pricing(
    current_user: dict = Depends(require_owner),
    db: Session = Depends(get_db)
):
    """
    Get current AI model pricing configuration.
    """
    pricing = db.execute(text("""
        SELECT
            provider, model_id, model_name,
            input_price_per_1m, output_price_per_1m,
            is_active, effective_date
        FROM ai_model_pricing
        WHERE is_active = true
        ORDER BY provider, model_id
    """)).fetchall()

    return {
        "pricing": [
            {
                "provider": p[0],
                "model_id": p[1],
                "model_name": p[2],
                "input_price_per_1m": float(p[3]),
                "output_price_per_1m": float(p[4]),
                "is_active": p[5],
                "effective_date": str(p[6])
            }
            for p in pricing
        ]
    }


# =============================================================================
# ALERTS
# =============================================================================

@router.get("/alerts")
async def get_usage_alerts(
    status: Optional[str] = Query(None, description="Filter by status: active, acknowledged, resolved"),
    limit: int = Query(50, ge=1, le=100),
    current_user: dict = Depends(require_owner),
    db: Session = Depends(get_db)
):
    """
    Get usage alerts.
    """
    params = {"limit": limit, "org_id": _require_org_id(current_user)}
    status_filter = ""

    if status:
        status_filter = "AND status = :status"
        params["status"] = status

    query = """
        SELECT
            id, scope_type, scope_id, category,
            alert_type, severity, title, message,
            threshold_value, actual_value,
            status, created_at, acknowledged_at, resolved_at
        FROM usage_alerts
        WHERE organization_id = :org_id
        """ + status_filter + """
        ORDER BY created_at DESC
        LIMIT :limit
    """
    alerts = db.execute(text(query), params).fetchall()

    return {
        "total": len(alerts),
        "alerts": [
            {
                "id": str(a[0]),
                "scope_type": a[1],
                "scope_id": a[2],
                "category": a[3],
                "alert_type": a[4],
                "severity": a[5],
                "title": a[6],
                "message": a[7],
                "threshold_value": float(a[8]) if a[8] else None,
                "actual_value": float(a[9]) if a[9] else None,
                "status": a[10],
                "created_at": a[11].isoformat() if a[11] else None,
                "acknowledged_at": a[12].isoformat() if a[12] else None,
                "resolved_at": a[13].isoformat() if a[13] else None
            }
            for a in alerts
        ]
    }


@router.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: str,
    current_user: dict = Depends(require_owner),
    db: Session = Depends(get_db)
):
    """
    Acknowledge a usage alert.
    """
    db.execute(text("""
        UPDATE usage_alerts
        SET status = 'acknowledged',
            acknowledged_by = :user_id,
            acknowledged_at = :now
        WHERE id = :alert_id
        AND organization_id = :org_id
    """), {
        "alert_id": alert_id,
        "org_id": _require_org_id(current_user),
        "user_id": current_user.get("id") if isinstance(current_user, dict) else getattr(current_user, 'id', None),
        "now": datetime.now(timezone.utc)
    })
    db.commit()

    return {"status": "acknowledged", "alert_id": alert_id}


@router.post("/alerts/{alert_id}/resolve")
async def resolve_alert(
    alert_id: str,
    current_user: dict = Depends(require_owner),
    db: Session = Depends(get_db)
):
    """
    Resolve a usage alert.
    """
    db.execute(text("""
        UPDATE usage_alerts
        SET status = 'resolved',
            resolved_at = :now
        WHERE id = :alert_id
        AND organization_id = :org_id
    """), {
        "alert_id": alert_id,
        "org_id": _require_org_id(current_user),
        "now": datetime.now(timezone.utc)
    })
    db.commit()

    return {"status": "resolved", "alert_id": alert_id}
