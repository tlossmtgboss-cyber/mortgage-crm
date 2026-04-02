"""
Lead Assignment Configuration Routes

Admin endpoints for configuring how leads are distributed to loan officers.
Covers: strategy config, routing rules CRUD, pool management, exceptions, testing, audit log.

All endpoints require authentication and admin/manager role.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import text
from db import get_db as _db_dep
from schemas.lead_assignment import (
    AssignmentConfigUpdate,
    AssignmentConfigResponse,
    RuleCreate,
    RuleUpdate,
    RuleResponse,
    PoolMemberCreate,
    PoolMemberUpdate,
    PoolMemberResponse,
    ExceptionCreate,
    ExceptionResponse,
    TestAssignmentRequest,
    TestAssignmentResponse,
    AuditLogEntry,
    ReassignRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/admin/lead-assignment",
    tags=["Lead Assignment"],
)


# =============================================================================
# Dependency Injection
# =============================================================================

_get_current_user = None
_User = None


def set_dependencies(user_model, current_user_func, db_func=None):
    """Set dependencies for the routes."""
    global _User, _get_current_user
    _User = user_model
    _get_current_user = current_user_func


async def _resolve_current_user(
    request: Request,
    db: Session = Depends(_db_dep),
):
    """Resolve the current user via the injected auth function."""
    if _get_current_user is None:
        raise HTTPException(status_code=500, detail="Dependencies not configured")
    auth = request.headers.get("Authorization", "")
    token = auth[7:] if auth.startswith("Bearer ") else ""
    return await _get_current_user(token, request, db)


def _require_admin(current_user):
    """Check that user has admin or manager permissions."""
    role = getattr(current_user, "role", "")
    is_admin = getattr(current_user, "is_admin", False)
    if not is_admin and role not in ("admin", "manager", "platform_admin", "site_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


def _get_org_id(current_user) -> int:
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=400, detail="No organization associated with user")
    return org_id


def success_response(data, message: str = "Success"):
    return {
        "success": True,
        "message": message,
        "data": data,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# =============================================================================
# CONFIG ENDPOINTS
# =============================================================================

@router.get("/config")
async def get_config(
    db: Session = Depends(_db_dep),
    current_user=Depends(_resolve_current_user),
):
    """Get lead assignment configuration for the organization."""
    from services.lead_assignment_service import get_or_create_config

    _require_admin(current_user)
    org_id = _get_org_id(current_user)

    config = get_or_create_config(db, org_id)

    return success_response(
        data={
            "id": config.id,
            "organization_id": config.organization_id,
            "strategy": config.strategy,
            "fallback_user_id": config.fallback_user_id,
            "respect_capacity": config.respect_capacity,
            "max_daily_leads_per_user": config.max_daily_leads_per_user,
            "business_hours_only": config.business_hours_only,
            "business_hours_start": config.business_hours_start,
            "business_hours_end": config.business_hours_end,
            "business_hours_timezone": config.business_hours_timezone,
            "notify_on_assignment": config.notify_on_assignment,
            "notification_channels": config.notification_channels or ["email"],
            "round_robin_index": config.round_robin_index or 0,
            "dedup_enabled": config.dedup_enabled,
            "dedup_match_fields": config.dedup_match_fields or ["email", "phone"],
            "dedup_window_days": config.dedup_window_days or 30,
            "dedup_action": config.dedup_action or "merge",
            "is_active": config.is_active,
            "updated_at": config.updated_at.isoformat() if config.updated_at else None,
        },
        message="Assignment configuration retrieved",
    )


@router.put("/config")
async def update_config(
    update: AssignmentConfigUpdate,
    db: Session = Depends(_db_dep),
    current_user=Depends(_resolve_current_user),
):
    """Update lead assignment configuration."""
    from services.lead_assignment_service import get_or_create_config

    _require_admin(current_user)
    org_id = _get_org_id(current_user)

    config = get_or_create_config(db, org_id)

    for field, value in update.dict(exclude_unset=True).items():
        setattr(config, field, value)

    config.updated_by_user_id = current_user.id
    db.commit()

    return success_response(
        data={"strategy": config.strategy},
        message=f"Assignment strategy updated to '{config.strategy}'",
    )


# =============================================================================
# RULE ENDPOINTS
# =============================================================================

@router.get("/rules")
async def list_rules(
    db: Session = Depends(_db_dep),
    current_user=Depends(_resolve_current_user),
):
    """List all assignment rules for the organization."""
    from database.models.lead_assignment import LeadAssignmentRule

    _require_admin(current_user)
    org_id = _get_org_id(current_user)

    rules = db.query(LeadAssignmentRule).filter(
        LeadAssignmentRule.organization_id == org_id,
    ).order_by(LeadAssignmentRule.priority.asc()).all()

    return success_response(
        data=[
            {
                "id": r.id,
                "rule_name": r.rule_name,
                "description": r.description,
                "priority": r.priority,
                "conditions": r.conditions,
                "match_type": r.match_type,
                "target_type": r.target_type,
                "target_config": r.target_config,
                "is_active": r.is_active,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            }
            for r in rules
        ],
        message=f"{len(rules)} rules found",
    )


@router.post("/rules")
async def create_rule(
    rule: RuleCreate,
    db: Session = Depends(_db_dep),
    current_user=Depends(_resolve_current_user),
):
    """Create a new assignment rule."""
    from database.models.lead_assignment import LeadAssignmentRule

    _require_admin(current_user)
    org_id = _get_org_id(current_user)

    new_rule = LeadAssignmentRule(
        organization_id=org_id,
        rule_name=rule.rule_name,
        description=rule.description,
        priority=rule.priority,
        conditions=[c.dict() for c in rule.conditions],
        match_type=rule.match_type,
        target_type=rule.target_type,
        target_config=rule.target_config,
        created_by_user_id=current_user.id,
    )
    db.add(new_rule)
    db.commit()
    db.refresh(new_rule)

    return success_response(
        data={"id": new_rule.id, "rule_name": new_rule.rule_name},
        message=f"Rule '{new_rule.rule_name}' created",
    )


@router.put("/rules/{rule_id}")
async def update_rule(
    rule_id: int,
    update: RuleUpdate,
    db: Session = Depends(_db_dep),
    current_user=Depends(_resolve_current_user),
):
    """Update an assignment rule."""
    from database.models.lead_assignment import LeadAssignmentRule

    _require_admin(current_user)
    org_id = _get_org_id(current_user)

    rule = db.query(LeadAssignmentRule).filter(
        LeadAssignmentRule.id == rule_id,
        LeadAssignmentRule.organization_id == org_id,
    ).first()

    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    update_data = update.dict(exclude_unset=True)
    if "conditions" in update_data and update_data["conditions"]:
        update_data["conditions"] = [c.dict() if hasattr(c, "dict") else c for c in update_data["conditions"]]

    for field, value in update_data.items():
        setattr(rule, field, value)

    db.commit()

    return success_response(
        data={"id": rule.id},
        message=f"Rule '{rule.rule_name}' updated",
    )


@router.delete("/rules/{rule_id}")
async def delete_rule(
    rule_id: int,
    db: Session = Depends(_db_dep),
    current_user=Depends(_resolve_current_user),
):
    """Delete (deactivate) an assignment rule."""
    from database.models.lead_assignment import LeadAssignmentRule

    _require_admin(current_user)
    org_id = _get_org_id(current_user)

    rule = db.query(LeadAssignmentRule).filter(
        LeadAssignmentRule.id == rule_id,
        LeadAssignmentRule.organization_id == org_id,
    ).first()

    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    rule.is_active = False
    db.commit()

    return success_response(
        data={"id": rule.id},
        message=f"Rule '{rule.rule_name}' deactivated",
    )


# =============================================================================
# POOL ENDPOINTS
# =============================================================================

@router.get("/pool")
async def list_pool_members(
    db: Session = Depends(_db_dep),
    current_user=Depends(_resolve_current_user),
):
    """List all assignment pool members with current daily lead counts."""
    from database.models.lead_assignment import LeadAssignmentPool

    _require_admin(current_user)
    org_id = _get_org_id(current_user)

    members = db.query(LeadAssignmentPool).filter(
        LeadAssignmentPool.organization_id == org_id,
    ).all()

    # Get user names and daily counts in one query
    user_ids = [m.user_id for m in members]
    user_names = {}
    daily_counts = {}

    if user_ids:
        try:
            id_placeholders = ", ".join(f":uid_{i}" for i in range(len(user_ids)))
            id_params = {f"uid_{i}": uid for i, uid in enumerate(user_ids)}

            rows = db.execute(text(
                f"SELECT id, first_name || ' ' || last_name as name "
                f"FROM users WHERE id IN ({id_placeholders})"
            ), id_params).fetchall()
            user_names = {row[0]: row[1] for row in rows}

            id_params["org_id"] = org_id
            count_rows = db.execute(text(
                f"SELECT owner_id, COUNT(*) as cnt "
                f"FROM leads "
                f"WHERE owner_id IN ({id_placeholders}) AND organization_id = :org_id "
                f"AND created_at >= CURRENT_DATE "
                f"GROUP BY owner_id"
            ), id_params).fetchall()
            daily_counts = {row[0]: row[1] for row in count_rows}
        except Exception as e:
            logger.warning(f"Pool enrichment failed: {e}")

    return success_response(
        data=[
            {
                "id": m.id,
                "user_id": m.user_id,
                "user_name": user_names.get(m.user_id, f"User {m.user_id}"),
                "weight": m.weight,
                "max_daily_leads": m.max_daily_leads,
                "is_active": m.is_active,
                "geographic_states": m.geographic_states,
                "specialties": m.specialties,
                "current_daily_leads": daily_counts.get(m.user_id, 0),
            }
            for m in members
        ],
        message=f"{len(members)} pool members",
    )


@router.post("/pool")
async def add_pool_member(
    member: PoolMemberCreate,
    db: Session = Depends(_db_dep),
    current_user=Depends(_resolve_current_user),
):
    """Add a user to the assignment pool."""
    from database.models.lead_assignment import LeadAssignmentPool

    _require_admin(current_user)
    org_id = _get_org_id(current_user)

    # Check for duplicate
    existing = db.query(LeadAssignmentPool).filter(
        LeadAssignmentPool.organization_id == org_id,
        LeadAssignmentPool.user_id == member.user_id,
    ).first()

    if existing:
        # Reactivate if deactivated
        existing.is_active = True
        existing.weight = member.weight
        existing.max_daily_leads = member.max_daily_leads
        existing.geographic_states = member.geographic_states
        existing.specialties = member.specialties
        db.commit()
        return success_response(
            data={"id": existing.id},
            message="Pool member reactivated and updated",
        )

    new_member = LeadAssignmentPool(
        organization_id=org_id,
        user_id=member.user_id,
        weight=member.weight,
        max_daily_leads=member.max_daily_leads,
        geographic_states=member.geographic_states,
        specialties=member.specialties,
    )
    db.add(new_member)
    db.commit()
    db.refresh(new_member)

    return success_response(
        data={"id": new_member.id},
        message="User added to assignment pool",
    )


@router.put("/pool/{member_id}")
async def update_pool_member(
    member_id: int,
    update: PoolMemberUpdate,
    db: Session = Depends(_db_dep),
    current_user=Depends(_resolve_current_user),
):
    """Update a pool member's settings."""
    from database.models.lead_assignment import LeadAssignmentPool

    _require_admin(current_user)
    org_id = _get_org_id(current_user)

    member = db.query(LeadAssignmentPool).filter(
        LeadAssignmentPool.id == member_id,
        LeadAssignmentPool.organization_id == org_id,
    ).first()

    if not member:
        raise HTTPException(status_code=404, detail="Pool member not found")

    for field, value in update.dict(exclude_unset=True).items():
        setattr(member, field, value)

    db.commit()

    return success_response(
        data={"id": member.id},
        message="Pool member updated",
    )


@router.delete("/pool/{member_id}")
async def remove_pool_member(
    member_id: int,
    db: Session = Depends(_db_dep),
    current_user=Depends(_resolve_current_user),
):
    """Remove (deactivate) a pool member."""
    from database.models.lead_assignment import LeadAssignmentPool

    _require_admin(current_user)
    org_id = _get_org_id(current_user)

    member = db.query(LeadAssignmentPool).filter(
        LeadAssignmentPool.id == member_id,
        LeadAssignmentPool.organization_id == org_id,
    ).first()

    if not member:
        raise HTTPException(status_code=404, detail="Pool member not found")

    member.is_active = False
    db.commit()

    return success_response(
        data={"id": member.id},
        message="Pool member deactivated",
    )


# =============================================================================
# EXCEPTION ENDPOINTS
# =============================================================================

@router.get("/exceptions")
async def list_exceptions(
    active_only: bool = Query(True),
    db: Session = Depends(_db_dep),
    current_user=Depends(_resolve_current_user),
):
    """List assignment exceptions (PTO, blocked, etc.)."""
    from database.models.lead_assignment import LeadAssignmentException

    _require_admin(current_user)
    org_id = _get_org_id(current_user)

    query = db.query(LeadAssignmentException).filter(
        LeadAssignmentException.organization_id == org_id,
    )
    if active_only:
        query = query.filter(LeadAssignmentException.is_active == True)

    exceptions = query.order_by(LeadAssignmentException.starts_at.desc()).all()

    return success_response(
        data=[
            {
                "id": e.id,
                "user_id": e.user_id,
                "exception_type": e.exception_type,
                "reason": e.reason,
                "starts_at": e.starts_at.isoformat() if e.starts_at else None,
                "ends_at": e.ends_at.isoformat() if e.ends_at else None,
                "is_active": e.is_active,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in exceptions
        ],
        message=f"{len(exceptions)} exceptions found",
    )


@router.post("/exceptions")
async def create_exception(
    exc: ExceptionCreate,
    db: Session = Depends(_db_dep),
    current_user=Depends(_resolve_current_user),
):
    """Create an assignment exception (PTO, block, etc.)."""
    from database.models.lead_assignment import LeadAssignmentException

    _require_admin(current_user)
    org_id = _get_org_id(current_user)

    new_exc = LeadAssignmentException(
        organization_id=org_id,
        user_id=exc.user_id,
        exception_type=exc.exception_type,
        reason=exc.reason,
        starts_at=exc.starts_at,
        ends_at=exc.ends_at,
        created_by_user_id=current_user.id,
    )
    db.add(new_exc)
    db.commit()
    db.refresh(new_exc)

    return success_response(
        data={"id": new_exc.id},
        message=f"{exc.exception_type} exception created for user {exc.user_id}",
    )


@router.delete("/exceptions/{exception_id}")
async def cancel_exception(
    exception_id: int,
    db: Session = Depends(_db_dep),
    current_user=Depends(_resolve_current_user),
):
    """Cancel an assignment exception."""
    from database.models.lead_assignment import LeadAssignmentException

    _require_admin(current_user)
    org_id = _get_org_id(current_user)

    exc = db.query(LeadAssignmentException).filter(
        LeadAssignmentException.id == exception_id,
        LeadAssignmentException.organization_id == org_id,
    ).first()

    if not exc:
        raise HTTPException(status_code=404, detail="Exception not found")

    exc.is_active = False
    db.commit()

    return success_response(
        data={"id": exc.id},
        message="Exception cancelled",
    )


# =============================================================================
# TEST & REASSIGN ENDPOINTS
# =============================================================================

@router.post("/test")
async def test_assignment(
    test_lead: TestAssignmentRequest,
    db: Session = Depends(_db_dep),
    current_user=Depends(_resolve_current_user),
):
    """Test assignment: simulate which LO would receive a lead with given attributes."""
    from services.lead_assignment_service import assign_lead, get_or_create_config, _get_eligible_candidates

    _require_admin(current_user)
    org_id = _get_org_id(current_user)

    lead_data = test_lead.dict(exclude_unset=True)
    config = get_or_create_config(db, org_id)
    candidates = _get_eligible_candidates(db, org_id, config)

    result_user_id = assign_lead(
        db, lead_data, org_id,
        assigned_by=current_user.id,
        is_dry_run=True,
    )

    # Look up user name
    user_name = None
    if result_user_id:
        try:
            row = db.execute(text(
                "SELECT first_name || ' ' || last_name FROM users WHERE id = :uid"
            ), {"uid": result_user_id}).scalar()
            user_name = row
        except Exception:
            pass

    return success_response(
        data={
            "assigned_user_id": result_user_id,
            "assigned_user_name": user_name,
            "strategy_used": config.strategy,
            "candidates_evaluated": len(candidates),
            "is_dry_run": True,
        },
        message=f"Test: would assign to {'user ' + str(result_user_id) if result_user_id else 'no one (unassigned)'}",
    )


@router.post("/reassign")
async def reassign_lead_endpoint(
    req: ReassignRequest,
    db: Session = Depends(_db_dep),
    current_user=Depends(_resolve_current_user),
):
    """Reassign a lead to a different loan officer."""
    from services.lead_assignment_service import reassign_lead

    _require_admin(current_user)
    org_id = _get_org_id(current_user)

    # Load the lead
    try:
        from database.models import Lead
        lead = db.query(Lead).filter(
            Lead.id == req.lead_id,
            Lead.organization_id == org_id,
        ).first()
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to load lead")

    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    reassign_lead(
        db, lead, org_id,
        to_user_id=req.to_user_id,
        reassigned_by=current_user.id,
        reason=req.reason,
    )
    db.commit()

    return success_response(
        data={"lead_id": req.lead_id, "new_owner_id": req.to_user_id},
        message=f"Lead {req.lead_id} reassigned to user {req.to_user_id}",
    )


# =============================================================================
# AUDIT & STATS ENDPOINTS
# =============================================================================

@router.get("/audit-log")
async def get_audit_log(
    lead_id: Optional[int] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(_db_dep),
    current_user=Depends(_resolve_current_user),
):
    """Get assignment audit log."""
    from database.models.lead_assignment import LeadAssignmentAuditLog

    _require_admin(current_user)
    org_id = _get_org_id(current_user)

    query = db.query(LeadAssignmentAuditLog).filter(
        LeadAssignmentAuditLog.organization_id == org_id,
    )

    if lead_id:
        query = query.filter(LeadAssignmentAuditLog.lead_id == lead_id)

    total = query.count()
    entries = query.order_by(
        LeadAssignmentAuditLog.created_at.desc()
    ).offset(offset).limit(limit).all()

    return success_response(
        data={
            "total": total,
            "entries": [
                {
                    "id": e.id,
                    "lead_id": e.lead_id,
                    "action": e.action,
                    "strategy_used": e.strategy_used,
                    "rule_name": e.rule_name,
                    "from_user_id": e.from_user_id,
                    "to_user_id": e.to_user_id,
                    "decision_reason": e.decision_reason,
                    "created_at": e.created_at.isoformat() if e.created_at else None,
                }
                for e in entries
            ],
        },
        message=f"{len(entries)} audit entries (of {total})",
    )


@router.get("/stats")
async def get_stats(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(_db_dep),
    current_user=Depends(_resolve_current_user),
):
    """Get assignment statistics and distribution metrics."""
    from services.lead_assignment_service import get_assignment_stats

    _require_admin(current_user)
    org_id = _get_org_id(current_user)

    stats = get_assignment_stats(db, org_id, days)

    return success_response(
        data=stats,
        message=f"Stats for last {days} days",
    )
