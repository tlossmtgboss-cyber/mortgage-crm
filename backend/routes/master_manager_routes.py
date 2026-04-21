"""
Master Manager Platform - API Routes
Capacity tracking, talent state, performance, and recruiting endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Optional, Dict, Any
from datetime import datetime, date, timezone, timedelta
from pydantic import BaseModel, Field

from database import get_db
from services.capacity_service import CapacityService, get_capacity_service
from services.performance_service import PerformanceService, get_performance_service
from services.risk_detection_service import RiskDetectionService, get_risk_detection_service
from sqlalchemy.exc import SQLAlchemyError
import os


_ADMIN_API_KEY = os.getenv("ADMIN_API_KEY")

_security = HTTPBearer(auto_error=False)


async def _require_auth(
    credentials: HTTPAuthorizationCredentials = Depends(_security),
):
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    from auth.dependencies import get_current_user_flexible
    from database import get_db as db_getter
    db = next(db_getter())
    try:
        user = await get_current_user_flexible(token=credentials.credentials, request=None, db=db)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid token")
        return user
    finally:
        db.close()


router = APIRouter(
    prefix="/api/v1/master-manager",
    tags=["Master Manager"],
    dependencies=[Depends(_require_auth)],
)


# =============================================================================
# PYDANTIC MODELS
# =============================================================================

class CapacityLimitsUpdate(BaseModel):
    max_files: Optional[int] = Field(None, ge=1, le=100)
    max_leads: Optional[int] = Field(None, ge=1, le=500)
    max_tasks: Optional[int] = Field(None, ge=1, le=100)


class AvailabilityUpdate(BaseModel):
    is_available: bool
    status: str = "active"  # active, on_leave, training, suspended
    return_date: Optional[date] = None
    notes: Optional[str] = None


class TalentStateUpdate(BaseModel):
    state: str
    reason: Optional[str] = None


class RoleDefinitionCreate(BaseModel):
    role_name: str
    role_category: str = "operations"
    description: Optional[str] = None
    default_max_files: int = 25
    default_max_leads: int = 50
    default_max_tasks_daily: int = 30
    expected_throughput: Optional[Dict[str, Any]] = None
    learning_curve_days: int = 90
    replacement_difficulty: int = 5
    required_skills: Optional[List[str]] = None


class UserCapacityCreate(BaseModel):
    user_id: int
    role_definition_id: Optional[int] = None
    max_files_concurrent: int = 25
    max_leads_concurrent: int = 50
    max_tasks_daily: int = 30


# =============================================================================
# CAPACITY COMMAND CENTER ROUTES
# =============================================================================

@router.get("/capacity/overview")
async def get_capacity_overview(
    organization_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Get team-level capacity overview."""
    service = get_capacity_service(db)
    overview = await service.get_team_capacity_overview(organization_id)

    return {
        "total_members": overview.total_members,
        "status_breakdown": {
            "available": overview.available_count,
            "near_capacity": overview.near_capacity_count,
            "at_capacity": overview.at_capacity_count,
            "over_capacity": overview.over_capacity_count
        },
        "avg_capacity_pct": overview.avg_capacity_pct,
        "file_capacity": {
            "total": overview.total_file_capacity,
            "used": overview.used_file_capacity,
            "available": overview.total_file_capacity - overview.used_file_capacity,
            "utilization_pct": round((overview.used_file_capacity / max(overview.total_file_capacity, 1)) * 100, 1)
        },
        "alerts": {
            "surge_risk": overview.surge_risk,
            "bottleneck_roles": overview.bottleneck_roles
        }
    }


@router.get("/capacity/by-role")
async def get_capacity_by_role(
    organization_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Get capacity metrics grouped by role."""
    service = get_capacity_service(db)
    by_role = await service.get_capacity_by_role(organization_id)

    return {
        "roles": by_role,
        "total_roles": len(by_role)
    }


@router.get("/capacity/users")
async def get_all_user_capacities(
    organization_id: Optional[int] = None,
    status: Optional[str] = Query(None, description="Filter by capacity status"),
    role: Optional[str] = Query(None, description="Filter by role name"),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db)
):
    """Get capacity metrics for all users."""
    service = get_capacity_service(db)
    users = await service.get_all_user_capacities(
        organization_id=organization_id,
        status_filter=status,
        role_filter=role,
        limit=limit
    )

    return {
        "users": users,
        "total": len(users)
    }


@router.get("/capacity/user/{user_id}")
async def get_user_capacity(
    user_id: int,
    organization_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Get detailed capacity metrics for a specific user."""
    service = get_capacity_service(db)
    try:
        metrics = await service.calculate_user_capacity(user_id, organization_id)
        return {
            "user_id": metrics.user_id,
            "user_name": metrics.user_name,
            "role_name": metrics.role_name,
            "current": {
                "files": metrics.current_files,
                "leads": metrics.current_leads,
                "tasks": metrics.current_tasks
            },
            "limits": {
                "max_files": metrics.max_files,
                "max_leads": metrics.max_leads,
                "max_tasks": metrics.max_tasks
            },
            "capacity_pct": {
                "files": metrics.file_capacity_pct,
                "leads": metrics.lead_capacity_pct,
                "tasks": metrics.task_capacity_pct,
                "overall": metrics.overall_capacity_pct
            },
            "status": metrics.capacity_status,
            "is_available": metrics.is_available,
            "risk": {
                "burnout": metrics.burnout_risk,
                "attrition": metrics.attrition_risk
            }
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail="Not found")


@router.put("/capacity/user/{user_id}/limits")
async def update_user_capacity_limits(
    user_id: int,
    limits: CapacityLimitsUpdate,
    organization_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Update capacity limits for a user."""
    service = get_capacity_service(db)
    try:
        result = await service.update_user_capacity_limits(
            user_id=user_id,
            max_files=limits.max_files,
            max_leads=limits.max_leads,
            max_tasks=limits.max_tasks,
            organization_id=organization_id
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Bad request")


@router.put("/capacity/user/{user_id}/availability")
async def update_user_availability(
    user_id: int,
    availability: AvailabilityUpdate,
    organization_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Update user availability status."""
    service = get_capacity_service(db)
    result = await service.set_user_availability(
        user_id=user_id,
        is_available=availability.is_available,
        status=availability.status,
        return_date=availability.return_date,
        notes=availability.notes,
        organization_id=organization_id
    )
    return result


@router.post("/capacity/recalculate")
async def recalculate_all_capacities(
    organization_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Trigger recalculation of all user capacities."""
    service = get_capacity_service(db)
    count = await service.recalculate_all_capacities(organization_id)
    return {
        "message": f"Recalculated capacity for {count} users",
        "users_updated": count
    }


@router.post("/capacity/user")
async def create_user_capacity(
    data: UserCapacityCreate,
    organization_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Create capacity record for a user."""
    query = text("""
        INSERT INTO mm_talent_capacity (
            organization_id, user_id, role_definition_id,
            max_files_concurrent, max_leads_concurrent, max_tasks_daily,
            created_at, updated_at
        )
        VALUES (
            :org_id, :user_id, :role_id,
            :max_files, :max_leads, :max_tasks,
            CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        )
        ON CONFLICT (organization_id, user_id) DO UPDATE SET
            role_definition_id = EXCLUDED.role_definition_id,
            max_files_concurrent = EXCLUDED.max_files_concurrent,
            max_leads_concurrent = EXCLUDED.max_leads_concurrent,
            max_tasks_daily = EXCLUDED.max_tasks_daily,
            updated_at = CURRENT_TIMESTAMP
        RETURNING id
    """)

    result = db.execute(query, {
        "org_id": organization_id,
        "user_id": data.user_id,
        "role_id": data.role_definition_id,
        "max_files": data.max_files_concurrent,
        "max_leads": data.max_leads_concurrent,
        "max_tasks": data.max_tasks_daily
    }).fetchone()
    db.commit()

    # Calculate initial capacity
    service = get_capacity_service(db)
    metrics = await service.calculate_user_capacity(data.user_id, organization_id)

    return {
        "id": result.id,
        "user_id": data.user_id,
        "initial_capacity_pct": metrics.overall_capacity_pct,
        "status": metrics.capacity_status
    }


# =============================================================================
# ASSIGNMENT OPTIMIZATION ROUTES
# =============================================================================

@router.get("/assignment/suggest")
async def suggest_assignment(
    role: str,
    entity_type: str = Query("loan", description="lead, loan, or task"),
    complexity: str = Query("normal", description="simple, normal, or complex"),
    organization_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Get assignment recommendation based on capacity and performance."""
    service = get_capacity_service(db)
    suggestion = await service.suggest_optimal_assignment(
        entity_type=entity_type,
        role_needed=role,
        organization_id=organization_id,
        complexity=complexity
    )

    if not suggestion:
        return {
            "recommendation": None,
            "message": f"No available users found for role '{role}'"
        }

    return {
        "recommendation": {
            "user_id": suggestion["recommended_user_id"],
            "user_name": suggestion["recommended_user_name"],
            "role": suggestion["role"],
            "capacity_pct": suggestion["current_capacity_pct"],
            "available_slots": suggestion["available_slots"],
            "score": suggestion["recommendation_score"],
            "reasoning": suggestion["reasoning"]
        },
        "alternatives": suggestion["alternatives"]
    }


@router.get("/assignment/available")
async def get_available_users(
    role: str,
    min_capacity: float = Query(25, ge=0, le=100, description="Minimum available capacity %"),
    organization_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Get list of available users for a role."""
    service = get_capacity_service(db)
    available = await service.get_available_users_for_role(
        role_name=role,
        min_capacity_pct=min_capacity,
        organization_id=organization_id
    )

    return {
        "role": role,
        "available_users": available,
        "count": len(available)
    }


# =============================================================================
# ROLE DEFINITIONS ROUTES
# =============================================================================

@router.get("/roles")
async def get_role_definitions(
    organization_id: Optional[int] = None,
    category: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get all role definitions."""
    query = text("""
        SELECT
            id, role_name, role_category, description,
            default_max_files, default_max_leads, default_max_tasks_daily,
            expected_throughput, learning_curve_days, replacement_difficulty,
            required_skills, is_active, created_at
        FROM mm_role_definitions
        WHERE (:org_id IS NULL OR organization_id = :org_id OR organization_id IS NULL)
        AND (:category IS NULL OR role_category = :category)
        AND is_active = true
        ORDER BY role_category, role_name
    """)

    results = db.execute(query, {
        "org_id": organization_id,
        "category": category
    }).fetchall()

    return {
        "roles": [
            {
                "id": r.id,
                "role_name": r.role_name,
                "role_category": r.role_category,
                "description": r.description,
                "capacity_defaults": {
                    "max_files": r.default_max_files,
                    "max_leads": r.default_max_leads,
                    "max_tasks": r.default_max_tasks_daily
                },
                "expected_throughput": r.expected_throughput,
                "learning_curve_days": r.learning_curve_days,
                "replacement_difficulty": r.replacement_difficulty,
                "required_skills": r.required_skills or []
            }
            for r in results
        ],
        "total": len(results)
    }


@router.post("/roles")
async def create_role_definition(
    role: RoleDefinitionCreate,
    organization_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Create a new role definition."""
    query = text("""
        INSERT INTO mm_role_definitions (
            organization_id, role_name, role_category, description,
            default_max_files, default_max_leads, default_max_tasks_daily,
            expected_throughput, learning_curve_days, replacement_difficulty,
            required_skills, created_at, updated_at
        )
        VALUES (
            :org_id, :role_name, :role_category, :description,
            :max_files, :max_leads, :max_tasks,
            :throughput, :learning_days, :replacement,
            :skills, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        )
        RETURNING id
    """)

    import json
    result = db.execute(query, {
        "org_id": organization_id,
        "role_name": role.role_name,
        "role_category": role.role_category,
        "description": role.description,
        "max_files": role.default_max_files,
        "max_leads": role.default_max_leads,
        "max_tasks": role.default_max_tasks_daily,
        "throughput": json.dumps(role.expected_throughput) if role.expected_throughput else "{}",
        "learning_days": role.learning_curve_days,
        "replacement": role.replacement_difficulty,
        "skills": json.dumps(role.required_skills) if role.required_skills else "[]"
    }).fetchone()
    db.commit()

    return {
        "id": result.id,
        "role_name": role.role_name,
        "message": f"Role '{role.role_name}' created successfully"
    }


# =============================================================================
# TALENT STATE ROUTES
# =============================================================================

@router.get("/talent/readiness")
async def get_talent_readiness_board(
    organization_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Get talent readiness board - users grouped by state."""
    query = text("""
        SELECT
            ts.state,
            COUNT(*) as count,
            json_agg(json_build_object(
                'user_id', ts.user_id,
                'user_name', u.full_name,
                'role', rd.role_name,
                'state_reason', ts.state_reason,
                'state_changed_at', ts.state_changed_at,
                'capacity_pct', tc.overall_capacity_pct,
                'is_new_hire', ts.is_new_hire,
                'ramp_progress', ts.ramp_progress_pct,
                'promotion_eligible', ts.promotion_eligible
            )) as users
        FROM mm_talent_state ts
        JOIN users u ON u.id = ts.user_id
        LEFT JOIN mm_talent_capacity tc ON tc.user_id = ts.user_id
        LEFT JOIN mm_role_definitions rd ON rd.id = tc.role_definition_id
        WHERE (:org_id IS NULL OR ts.organization_id = :org_id)
        GROUP BY ts.state
        ORDER BY ts.state
    """)

    results = db.execute(query, {"org_id": organization_id}).fetchall()

    # Organize into board columns
    board = {
        "active": [],
        "near_capacity": [],
        "over_capacity": [],
        "new_hire": [],
        "bench_training": [],
        "bench_warm": [],
        "promotion_ready": [],
        "at_risk": [],
        "exit_likely": [],
        "on_leave": []
    }

    for r in results:
        if r.state in board:
            board[r.state] = r.users or []

    return {
        "board": board,
        "summary": {
            state: len(users) for state, users in board.items()
        }
    }


@router.put("/talent/{user_id}/state")
async def update_talent_state(
    user_id: int,
    state_update: TalentStateUpdate,
    changed_by: Optional[int] = None,
    organization_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Update talent state for a user."""
    # Get current state for history
    current = db.execute(text("""
        SELECT state, overall_capacity_pct
        FROM mm_talent_state ts
        LEFT JOIN mm_talent_capacity tc ON tc.user_id = ts.user_id
        WHERE ts.user_id = :user_id
    """), {"user_id": user_id}).fetchone()

    # Update state
    query = text("""
        UPDATE mm_talent_state
        SET
            state = :new_state,
            state_reason = :reason,
            state_changed_at = CURRENT_TIMESTAMP,
            state_changed_by = :changed_by,
            updated_at = CURRENT_TIMESTAMP
        WHERE user_id = :user_id
        AND (:org_id IS NULL OR organization_id = :org_id)
        RETURNING *
    """)

    result = db.execute(query, {
        "user_id": user_id,
        "new_state": state_update.state,
        "reason": state_update.reason,
        "changed_by": changed_by,
        "org_id": organization_id
    }).fetchone()

    if not result:
        raise HTTPException(status_code=404, detail=f"Talent state not found for user {user_id}")

    # Add to history
    history_query = text("""
        INSERT INTO mm_talent_state_history (
            organization_id, user_id, previous_state, new_state,
            reason, changed_by, capacity_pct_at_change, created_at
        )
        VALUES (
            :org_id, :user_id, :prev_state, :new_state,
            :reason, :changed_by, :capacity, CURRENT_TIMESTAMP
        )
    """)

    db.execute(history_query, {
        "org_id": organization_id,
        "user_id": user_id,
        "prev_state": current.state if current else None,
        "new_state": state_update.state,
        "reason": state_update.reason,
        "changed_by": changed_by,
        "capacity": current.overall_capacity_pct if current else None
    })
    db.commit()

    return {
        "user_id": user_id,
        "previous_state": current.state if current else None,
        "new_state": state_update.state,
        "reason": state_update.reason
    }


@router.get("/talent/{user_id}/state")
async def get_talent_state(
    user_id: int,
    organization_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Get talent state for a user."""
    query = text("""
        SELECT
            ts.*,
            u.full_name,
            rd.role_name
        FROM mm_talent_state ts
        JOIN users u ON u.id = ts.user_id
        LEFT JOIN mm_talent_capacity tc ON tc.user_id = ts.user_id
        LEFT JOIN mm_role_definitions rd ON rd.id = tc.role_definition_id
        WHERE ts.user_id = :user_id
        AND (:org_id IS NULL OR ts.organization_id = :org_id)
    """)

    result = db.execute(query, {
        "user_id": user_id,
        "org_id": organization_id
    }).fetchone()

    if not result:
        raise HTTPException(status_code=404, detail=f"Talent state not found for user {user_id}")

    return {
        "user_id": result.user_id,
        "user_name": result.full_name,
        "role_name": result.role_name,
        "state": result.state,
        "state_reason": result.state_reason,
        "state_changed_at": result.state_changed_at.isoformat() if result.state_changed_at else None,
        "new_hire": {
            "is_new_hire": result.is_new_hire,
            "is_in_ramp": result.is_in_ramp,
            "hire_date": result.hire_date.isoformat() if result.hire_date else None,
            "ramp_day": result.ramp_day,
            "ramp_progress_pct": result.ramp_progress_pct
        },
        "promotion": {
            "eligible": result.promotion_eligible,
            "readiness_score": result.promotion_readiness_score,
            "blocked_reason": result.promotion_blocked_reason
        },
        "pip": {
            "has_active": result.has_active_pip,
            "start_date": result.pip_start_date.isoformat() if result.pip_start_date else None,
            "end_date": result.pip_end_date.isoformat() if result.pip_end_date else None
        },
        "exit_risk": {
            "level": result.exit_risk_level,
            "factors": result.exit_risk_factors
        }
    }


# =============================================================================
# ALERTS ROUTES
# =============================================================================

@router.get("/alerts")
async def get_capacity_alerts(
    organization_id: Optional[int] = None,
    status: str = Query("open", description="open, acknowledged, resolved, all"),
    severity: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db)
):
    """Get capacity and risk alerts."""
    status_filter = "AND status = :status" if status != "all" else ""

    sql = (
        "SELECT"
        " a.*,"
        " u.full_name as user_name,"
        " rd.role_name"
        " FROM mm_capacity_alerts a"
        " LEFT JOIN users u ON u.id = a.user_id"
        " LEFT JOIN mm_role_definitions rd ON rd.id = a.role_definition_id"
        " WHERE (:org_id IS NULL OR a.organization_id = :org_id)"
        " " + status_filter +
        " AND (:severity IS NULL OR a.severity = :severity)"
        " ORDER BY"
        " CASE a.severity"
        " WHEN 'critical' THEN 1"
        " WHEN 'warning' THEN 2"
        " ELSE 3"
        " END,"
        " a.created_at DESC"
        " LIMIT :limit"
    )
    query = text(sql)

    results = db.execute(query, {
        "org_id": organization_id,
        "status": status if status != "all" else None,
        "severity": severity,
        "limit": limit
    }).fetchall()

    return {
        "alerts": [
            {
                "id": r.id,
                "alert_type": r.alert_type,
                "severity": r.severity,
                "title": r.title,
                "description": r.description,
                "user_id": r.user_id,
                "user_name": r.user_name,
                "role_name": r.role_name,
                "status": r.status,
                "metrics": r.metrics_snapshot,
                "recommended_actions": r.recommended_actions,
                "created_at": r.created_at.isoformat()
            }
            for r in results
        ],
        "total": len(results)
    }


@router.put("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: int,
    acknowledged_by: int,
    db: Session = Depends(get_db)
):
    """Acknowledge an alert."""
    query = text("""
        UPDATE mm_capacity_alerts
        SET
            status = 'acknowledged',
            acknowledged_at = CURRENT_TIMESTAMP,
            acknowledged_by = :by_user
        WHERE id = :alert_id
        RETURNING id, title
    """)

    result = db.execute(query, {
        "alert_id": alert_id,
        "by_user": acknowledged_by
    }).fetchone()
    db.commit()

    if not result:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")

    return {
        "id": result.id,
        "title": result.title,
        "status": "acknowledged"
    }


@router.put("/alerts/{alert_id}/resolve")
async def resolve_alert(
    alert_id: int,
    resolved_by: int,
    notes: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Resolve an alert."""
    query = text("""
        UPDATE mm_capacity_alerts
        SET
            status = 'resolved',
            resolved_at = CURRENT_TIMESTAMP,
            resolved_by = :by_user,
            resolution_notes = :notes
        WHERE id = :alert_id
        RETURNING id, title
    """)

    result = db.execute(query, {
        "alert_id": alert_id,
        "by_user": resolved_by,
        "notes": notes
    }).fetchone()
    db.commit()

    if not result:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")

    return {
        "id": result.id,
        "title": result.title,
        "status": "resolved"
    }


# =============================================================================
# PERFORMANCE ROUTES
# =============================================================================

@router.get("/performance/dashboard")
async def get_performance_dashboard(
    period_type: str = Query("monthly", description="daily, weekly, or monthly"),
    organization_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Get performance dashboard summary with leaderboard and trends."""
    service = get_performance_service(db)
    dashboard = await service.get_performance_dashboard(
        period_type=period_type,
        organization_id=organization_id
    )
    return dashboard


@router.get("/performance/leaderboard")
async def get_performance_leaderboard(
    period_type: str = Query("monthly", description="daily, weekly, or monthly"),
    period_start: Optional[date] = None,
    organization_id: Optional[int] = None,
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Get performance leaderboard for the specified period."""
    service = get_performance_service(db)
    leaderboard = await service.get_performance_leaderboard(
        period_type=period_type,
        period_start=period_start,
        organization_id=organization_id,
        limit=limit
    )
    return {
        "period_type": period_type,
        "period_start": period_start.isoformat() if period_start else None,
        "leaderboard": leaderboard,
        "total": len(leaderboard)
    }


@router.get("/performance/user/{user_id}")
async def get_user_performance(
    user_id: int,
    period_type: str = Query("monthly", description="daily, weekly, or monthly"),
    limit: int = Query(12, ge=1, le=24),
    organization_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Get performance history for a specific user."""
    service = get_performance_service(db)
    history = await service.get_user_performance(
        user_id=user_id,
        period_type=period_type,
        limit=limit,
        organization_id=organization_id
    )

    if not history:
        return {
            "user_id": user_id,
            "period_type": period_type,
            "history": [],
            "message": "No performance data found for this user"
        }

    return {
        "user_id": user_id,
        "user_name": history[0]["user_name"] if history else None,
        "period_type": period_type,
        "history": history,
        "total_periods": len(history)
    }


@router.post("/performance/calculate/daily")
async def calculate_daily_performance(
    target_date: Optional[date] = None,
    user_id: Optional[int] = None,
    organization_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """
    Calculate daily performance.
    If user_id is provided, calculates for that user only.
    Otherwise, calculates for all users.
    """
    service = get_performance_service(db)
    calc_date = target_date or (date.today() - timedelta(days=1))

    if user_id:
        try:
            metrics = await service.calculate_daily_performance(
                user_id=user_id,
                target_date=calc_date,
                organization_id=organization_id
            )
            return {
                "message": f"Calculated daily performance for user {user_id}",
                "date": calc_date.isoformat(),
                "user_id": user_id,
                "overall_score": metrics.overall_score,
                "grade": metrics.performance_grade
            }
        except ValueError as e:
            raise HTTPException(status_code=404, detail="Not found")
    else:
        count = await service.calculate_all_daily_performance(
            target_date=calc_date,
            organization_id=organization_id
        )
        return {
            "message": f"Calculated daily performance for {count} users",
            "date": calc_date.isoformat(),
            "users_calculated": count
        }


@router.post("/performance/calculate/weekly")
async def calculate_weekly_performance(
    week_start: Optional[date] = None,
    user_id: Optional[int] = None,
    organization_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """
    Calculate weekly performance.
    week_start should be a Monday. If not provided, uses the start of last week.
    """
    service = get_performance_service(db)

    # Default to start of last week
    if week_start is None:
        today = date.today()
        # Go back to Monday of last week
        days_since_monday = today.weekday()
        week_start = today - timedelta(days=days_since_monday + 7)

    if user_id:
        try:
            metrics = await service.calculate_weekly_performance(
                user_id=user_id,
                week_start=week_start,
                organization_id=organization_id
            )
            return {
                "message": f"Calculated weekly performance for user {user_id}",
                "week_start": week_start.isoformat(),
                "user_id": user_id,
                "overall_score": metrics.overall_score,
                "grade": metrics.performance_grade
            }
        except ValueError as e:
            raise HTTPException(status_code=404, detail="Not found")
    else:
        count = await service.calculate_all_weekly_performance(
            week_start=week_start,
            organization_id=organization_id
        )
        return {
            "message": f"Calculated weekly performance for {count} users",
            "week_start": week_start.isoformat(),
            "users_calculated": count
        }


@router.post("/performance/calculate/monthly")
async def calculate_monthly_performance(
    month_start: Optional[date] = None,
    user_id: Optional[int] = None,
    organization_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """
    Calculate monthly performance.
    month_start should be the 1st of the month. If not provided, uses the start of last month.
    """
    service = get_performance_service(db)

    # Default to start of last month
    if month_start is None:
        today = date.today()
        if today.month == 1:
            month_start = date(today.year - 1, 12, 1)
        else:
            month_start = date(today.year, today.month - 1, 1)

    if user_id:
        try:
            metrics = await service.calculate_monthly_performance(
                user_id=user_id,
                month_start=month_start,
                organization_id=organization_id
            )
            return {
                "message": f"Calculated monthly performance for user {user_id}",
                "month_start": month_start.isoformat(),
                "user_id": user_id,
                "overall_score": metrics.overall_score,
                "grade": metrics.performance_grade
            }
        except ValueError as e:
            raise HTTPException(status_code=404, detail="Not found")
    else:
        count = await service.calculate_all_monthly_performance(
            month_start=month_start,
            organization_id=organization_id
        )
        return {
            "message": f"Calculated monthly performance for {count} users",
            "month_start": month_start.isoformat(),
            "users_calculated": count
        }


@router.get("/performance/promotion-candidates")
async def get_promotion_candidates(
    min_score: float = Query(85, ge=0, le=100, description="Minimum average score"),
    min_months: int = Query(3, ge=1, le=12, description="Minimum months of sustained performance"),
    organization_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Get list of users who are potential promotion candidates based on sustained high performance."""
    service = get_performance_service(db)
    candidates = await service.identify_promotion_candidates(
        organization_id=organization_id,
        min_score=min_score,
        min_months=min_months
    )
    return {
        "criteria": {
            "min_score": min_score,
            "min_months": min_months
        },
        "candidates": candidates,
        "total": len(candidates)
    }


# =============================================================================
# RISK DETECTION ROUTES
# =============================================================================

@router.get("/risk/dashboard")
async def get_risk_dashboard(
    organization_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Get comprehensive risk dashboard with all risk metrics."""
    service = get_risk_detection_service(db)
    dashboard = await service.get_risk_dashboard(organization_id)
    return dashboard


@router.get("/risk/burnout")
async def get_all_burnout_risks(
    min_risk_score: float = Query(0, ge=0, le=100, description="Minimum risk score filter"),
    organization_id: Optional[int] = None,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db)
):
    """Get burnout risk assessment for all users."""
    service = get_risk_detection_service(db)
    risks = await service.get_all_burnout_risks(
        organization_id=organization_id,
        min_risk_score=min_risk_score,
        limit=limit
    )
    return {
        "risks": [
            {
                "user_id": r.user_id,
                "user_name": r.user_name,
                "role_name": r.role_name,
                "overall_risk_score": r.overall_risk_score,
                "risk_level": r.risk_level,
                "contributing_factors": r.contributing_factors,
                "recommendations": r.recommendations
            }
            for r in risks
        ],
        "total": len(risks),
        "high_risk_count": len([r for r in risks if r.risk_level in ["high", "critical"]])
    }


@router.get("/risk/burnout/{user_id}")
async def get_user_burnout_risk(
    user_id: int,
    organization_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Get detailed burnout risk assessment for a specific user."""
    service = get_risk_detection_service(db)
    try:
        assessment = await service.calculate_burnout_risk(user_id, organization_id)
        return {
            "user_id": assessment.user_id,
            "user_name": assessment.user_name,
            "role_name": assessment.role_name,
            "overall_risk_score": assessment.overall_risk_score,
            "risk_level": assessment.risk_level,
            "factor_scores": assessment.factor_scores,
            "contributing_factors": assessment.contributing_factors,
            "recommendations": assessment.recommendations,
            "trend": assessment.trend,
            "assessed_at": assessment.assessed_at.isoformat() if assessment.assessed_at else None
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail="Not found")


@router.get("/risk/attrition")
async def get_all_attrition_risks(
    min_risk_score: float = Query(0, ge=0, le=100, description="Minimum risk score filter"),
    organization_id: Optional[int] = None,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db)
):
    """Get attrition risk assessment for all users."""
    service = get_risk_detection_service(db)
    risks = await service.get_all_attrition_risks(
        organization_id=organization_id,
        min_risk_score=min_risk_score,
        limit=limit
    )
    return {
        "risks": [
            {
                "user_id": r.user_id,
                "user_name": r.user_name,
                "role_name": r.role_name,
                "overall_risk_score": r.overall_risk_score,
                "risk_level": r.risk_level,
                "contributing_factors": r.contributing_factors,
                "recommendations": r.recommendations
            }
            for r in risks
        ],
        "total": len(risks),
        "high_risk_count": len([r for r in risks if r.risk_level in ["high", "critical"]])
    }


@router.get("/risk/attrition/{user_id}")
async def get_user_attrition_risk(
    user_id: int,
    organization_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Get detailed attrition risk assessment for a specific user."""
    service = get_risk_detection_service(db)
    try:
        assessment = await service.calculate_attrition_risk(user_id, organization_id)
        return {
            "user_id": assessment.user_id,
            "user_name": assessment.user_name,
            "role_name": assessment.role_name,
            "overall_risk_score": assessment.overall_risk_score,
            "risk_level": assessment.risk_level,
            "factor_scores": assessment.factor_scores,
            "contributing_factors": assessment.contributing_factors,
            "recommendations": assessment.recommendations,
            "estimated_departure_window": assessment.estimated_departure_window,
            "assessed_at": assessment.assessed_at.isoformat() if assessment.assessed_at else None
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail="Not found")


@router.get("/risk/spof")
async def get_single_points_of_failure(
    organization_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Identify single points of failure - critical knowledge holders without backup."""
    service = get_risk_detection_service(db)
    spof_risks = await service.identify_single_points_of_failure(organization_id)
    return {
        "spof_risks": [
            {
                "user_id": r.user_id,
                "user_name": r.user_name,
                "role_name": r.role_name,
                "criticality_score": r.criticality_score,
                "risk_level": r.risk_level,
                "unique_capabilities": r.unique_capabilities,
                "coverage_gap": r.coverage_gap,
                "backup_users": r.backup_users,
                "knowledge_transfer_status": r.knowledge_transfer_status,
                "recommended_actions": r.recommended_actions
            }
            for r in spof_risks
        ],
        "total": len(spof_risks),
        "critical_count": len([r for r in spof_risks if r.risk_level == "critical"])
    }


@router.get("/risk/coverage-gaps")
async def get_coverage_gaps(
    organization_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Identify roles or capabilities with insufficient coverage."""
    service = get_risk_detection_service(db)
    gaps = await service.get_coverage_gaps(organization_id)
    return gaps


@router.get("/risk/key-dependencies")
async def get_key_person_dependencies(
    organization_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Identify key person dependencies across the organization."""
    service = get_risk_detection_service(db)
    dependencies = await service.get_key_person_dependencies(organization_id)
    return dependencies


@router.get("/risk/alerts")
async def get_risk_alerts(
    min_severity: str = Query("warning", description="Minimum severity: info, warning, high, critical"),
    organization_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Generate and return current risk alerts."""
    service = get_risk_detection_service(db)
    alerts = await service.generate_risk_alerts(
        organization_id=organization_id,
        min_severity=min_severity
    )
    return {
        "alerts": alerts,
        "total": len(alerts),
        "by_severity": {
            "critical": len([a for a in alerts if a["severity"] == "critical"]),
            "high": len([a for a in alerts if a["severity"] == "high"]),
            "warning": len([a for a in alerts if a["severity"] == "warning"]),
            "info": len([a for a in alerts if a["severity"] == "info"])
        }
    }


@router.post("/risk/calculate")
async def calculate_all_risks(
    organization_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Recalculate all risk scores for all users."""
    service = get_risk_detection_service(db)
    result = await service.calculate_all_risks(organization_id)
    return result


@router.post("/risk/calculate/{user_id}")
async def calculate_user_risks(
    user_id: int,
    organization_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Calculate all risk scores for a specific user."""
    service = get_risk_detection_service(db)
    try:
        burnout = await service.calculate_burnout_risk(user_id, organization_id)
        attrition = await service.calculate_attrition_risk(user_id, organization_id)

        return {
            "user_id": user_id,
            "burnout_risk": {
                "score": burnout.overall_risk_score,
                "level": burnout.risk_level
            },
            "attrition_risk": {
                "score": attrition.overall_risk_score,
                "level": attrition.risk_level
            },
            "calculated_at": datetime.now(timezone.utc).isoformat()
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail="Not found")


# =============================================================================
# ADMIN / MIGRATION ROUTES
# =============================================================================

@router.post("/admin/run-migration")
async def run_migration(
    admin_key: str = Header(..., alias="X-Admin-Key", description="Admin API key"),
    db: Session = Depends(get_db)
):
    """Run the Master Manager database migration."""
    if admin_key != _ADMIN_API_KEY or not _ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid admin key")

    try:
        from migrations.add_master_manager_tables import run_migration
        run_migration()
        return {"message": "Migration completed successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/admin/run-recruiting-migration")
async def run_recruiting_migration(
    admin_key: str = Header(..., alias="X-Admin-Key", description="Admin API key"),
    db: Session = Depends(get_db)
):
    """Run the Phase 2 Recruiting tables migration."""
    if admin_key != _ADMIN_API_KEY or not _ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid admin key")

    try:
        from migrations.add_recruiting_tables import run_migration
        result = run_migration()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/admin/fix-duplicate-roles")
async def fix_duplicate_roles(
    admin_key: str = Header(..., alias="X-Admin-Key", description="Admin API key"),
    db: Session = Depends(get_db)
):
    """Remove duplicate role definitions, keeping only one of each role_name."""
    if admin_key != _ADMIN_API_KEY or not _ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid admin key")

    try:
        # Delete duplicates keeping the lowest ID for each role_name
        delete_query = text("""
            DELETE FROM mm_role_definitions
            WHERE id NOT IN (
                SELECT MIN(id)
                FROM mm_role_definitions
                GROUP BY role_name
            )
        """)
        result = db.execute(delete_query)
        deleted_count = result.rowcount
        db.commit()

        # Get remaining roles
        roles_query = text("""
            SELECT id, role_name, role_category
            FROM mm_role_definitions
            ORDER BY role_category, role_name
        """)
        roles = db.execute(roles_query).fetchall()

        return {
            "message": f"Removed {deleted_count} duplicate roles",
            "remaining_roles": [
                {"id": r[0], "role_name": r[1], "role_category": r[2]}
                for r in roles
            ]
        }
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/admin/assign-role")
async def assign_role_to_user(
    admin_key: str = Header(..., alias="X-Admin-Key", description="Admin API key"),
    user_id: int = Query(..., description="User ID"),
    role_id: int = Query(..., description="Role definition ID"),
    db: Session = Depends(get_db)
):
    """Assign a role to a user's capacity record."""
    if admin_key != _ADMIN_API_KEY or not _ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid admin key")

    try:
        # Get role details
        role_query = text("""
            SELECT id, role_name, role_category,
                   default_max_files, default_max_leads, default_max_tasks_daily
            FROM mm_role_definitions
            WHERE id = :role_id
        """)
        role = db.execute(role_query, {"role_id": role_id}).fetchone()

        if not role:
            raise HTTPException(status_code=404, detail=f"Role {role_id} not found")

        # Get capacity defaults from role
        max_files = role.default_max_files or 25
        max_leads = role.default_max_leads or 50
        max_tasks = role.default_max_tasks_daily or 30

        # Update capacity record with role
        update_query = text("""
            UPDATE mm_talent_capacity
            SET role_definition_id = :role_id,
                max_files_concurrent = :max_files,
                max_leads_concurrent = :max_leads,
                max_tasks_daily = :max_tasks,
                updated_at = CURRENT_TIMESTAMP
            WHERE user_id = :user_id
            RETURNING id
        """)
        result = db.execute(update_query, {
            "role_id": role_id,
            "user_id": user_id,
            "max_files": max_files,
            "max_leads": max_leads,
            "max_tasks": max_tasks
        }).fetchone()
        db.commit()

        if not result:
            raise HTTPException(status_code=404, detail=f"No capacity record for user {user_id}")

        return {
            "message": f"Assigned role '{role.role_name}' to user {user_id}",
            "user_id": user_id,
            "role_id": role_id,
            "role_name": role.role_name,
            "capacity_limits": {
                "max_files": max_files,
                "max_leads": max_leads,
                "max_tasks": max_tasks
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/admin/fix-duplicate-capacities")
async def fix_duplicate_capacities(
    admin_key: str = Header(..., alias="X-Admin-Key", description="Admin API key"),
    db: Session = Depends(get_db)
):
    """Remove duplicate capacity records, keeping one per user."""
    if admin_key != _ADMIN_API_KEY or not _ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid admin key")

    try:
        delete_query = text("""
            DELETE FROM mm_talent_capacity
            WHERE id NOT IN (
                SELECT MIN(id)
                FROM mm_talent_capacity
                GROUP BY user_id
            )
        """)
        result = db.execute(delete_query)
        deleted_count = result.rowcount
        db.commit()

        return {
            "message": f"Removed {deleted_count} duplicate capacity records",
            "deleted_count": deleted_count
        }
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/admin/initialize-capacities")
async def initialize_capacities(
    admin_key: str = Header(..., alias="X-Admin-Key", description="Admin API key"),
    organization_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Initialize capacity records for all active users."""
    if admin_key != _ADMIN_API_KEY or not _ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid admin key")

    # Get all active users without capacity records
    query = text("""
        INSERT INTO mm_talent_capacity (organization_id, user_id, created_at, updated_at)
        SELECT
            u.organization_id,
            u.id,
            CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP
        FROM users u
        LEFT JOIN mm_talent_capacity tc ON tc.user_id = u.id
        WHERE u.is_active = true
        AND tc.id IS NULL
        AND (:org_id IS NULL OR u.organization_id = :org_id)
        RETURNING user_id
    """)

    results = db.execute(query, {"org_id": organization_id}).fetchall()
    db.commit()

    # Also create talent state records
    state_query = text("""
        INSERT INTO mm_talent_state (organization_id, user_id, state, created_at, updated_at)
        SELECT
            u.organization_id,
            u.id,
            'active',
            CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP
        FROM users u
        LEFT JOIN mm_talent_state ts ON ts.user_id = u.id
        WHERE u.is_active = true
        AND ts.id IS NULL
        AND (:org_id IS NULL OR u.organization_id = :org_id)
    """)

    db.execute(state_query, {"org_id": organization_id})
    db.commit()

    # Recalculate all capacities
    service = get_capacity_service(db)
    count = await service.recalculate_all_capacities(organization_id)

    return {
        "message": f"Initialized {len(results)} capacity records and calculated {count} users",
        "users_created": len(results),
        "users_calculated": count
    }
