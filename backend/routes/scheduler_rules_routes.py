"""
Scheduler Rules Routes -- API endpoints for the CalendarRulesEngine.

Provides CRUD access to scheduling rules and a dry-run validation endpoint.

Endpoints:
- GET  /rules/org-defaults         -- get org-level default rules
- PUT  /rules/org-defaults         -- update org defaults (admin only)
- GET  /rules/{lo_id}              -- get current rules for an LO
- PUT  /rules/{lo_id}              -- update rules for an LO (LO or admin)
- POST /rules/validate             -- validate a proposed booking (dry-run)

Note: This router is included in smart_scheduler_routes.py which provides
the /api/v1/scheduler prefix. Dependency injection follows the same
set_dependencies() pattern used by scheduler_routes.py.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional
import logging

from db import get_async_db
from services.calendar_rules_engine import (
    SchedulingRules,
    RuleViolation,
    DaySchedule,
    get_rules_for_lo,
    get_org_default_rules,
    save_rules_for_lo,
    save_org_default_rules,
    validate_booking_request,
    is_bookable,
    check_capacity,
    get_next_available,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# ============================================================================
# DEPENDENCY INJECTION STORAGE
# ============================================================================

_get_db = None
_get_current_user_func = None
_models = None


def set_dependencies(get_db_func, get_current_user_func, models_dict):
    """Set dependencies from parent module."""
    global _get_db, _get_current_user_func, _models
    _get_db = get_db_func
    _get_current_user_func = get_current_user_func
    _models = models_dict


async def _get_current_user(request: Request, db: AsyncSession = Depends(get_async_db)):
    """Resolve the current user via the injected auth function."""
    if _get_current_user_func is None:
        raise HTTPException(status_code=503, detail="Scheduler rules not initialized")
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else ""
    return await _get_current_user_func(token=token, request=request, db=db)


def _get_org_id(user) -> int:
    """Get organization_id from user, raise 403 if missing."""
    org_id = getattr(user, "organization_id", None)
    if org_id is None:
        raise HTTPException(status_code=403, detail="No organization context")
    return org_id


# ============================================================================
# REQUEST/RESPONSE SCHEMAS
# ============================================================================

class RulesUpdateRequest(BaseModel):
    """Request to update scheduling rules. All fields are optional (patch semantics)."""
    working_hours: Optional[Dict[str, DaySchedule]] = None
    buffer_before_minutes: Optional[int] = Field(None, ge=0, le=60)
    buffer_after_minutes: Optional[int] = Field(None, ge=0, le=60)
    lunch_break_start: Optional[str] = None
    lunch_break_end: Optional[str] = None
    enforce_lunch_break: Optional[bool] = None
    max_appointments_per_day: Optional[int] = Field(None, ge=1, le=50)
    max_appointments_per_week: Optional[int] = Field(None, ge=1, le=200)
    min_notice_hours: Optional[int] = Field(None, ge=0, le=168)
    max_advance_days: Optional[int] = Field(None, ge=1, le=365)
    min_duration_minutes: Optional[int] = Field(None, ge=5, le=60)
    max_duration_minutes: Optional[int] = Field(None, ge=15, le=480)
    duration_increment_minutes: Optional[int] = Field(None, ge=5, le=60)
    default_duration_minutes: Optional[int] = Field(None, ge=15, le=120)
    timezone: Optional[str] = None
    vip_can_override_notice: Optional[bool] = None
    vip_can_override_capacity: Optional[bool] = None
    vip_extended_hours_minutes: Optional[int] = Field(None, ge=0, le=120)


class ValidateBookingRequest(BaseModel):
    """Request to validate a proposed booking time (dry-run)."""
    lo_id: int
    proposed_start: datetime
    duration_minutes: int = Field(default=30, ge=5, le=480)
    is_vip: bool = False


# ============================================================================
# ROUTES
# ============================================================================

@router.get("/rules/org-defaults")
async def get_org_defaults(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """Get organization-level default scheduling rules."""
    user = await _get_current_user(request, db)
    org_id = _get_org_id(user)

    rules = await get_org_default_rules(org_id, db)
    return {
        "rules": rules.dict(exclude={"lo_id"}),
        "source": rules.source,
        "org_id": org_id,
    }


@router.put("/rules/org-defaults")
async def update_org_defaults(
    update: RulesUpdateRequest,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """
    Update organization-level default scheduling rules.
    Requires admin role.
    """
    user = await _get_current_user(request, db)
    org_id = _get_org_id(user)

    # Check admin role
    user_role = getattr(user, "role", None)
    if user_role not in ("admin", "site_admin", "platform_admin", "super_admin"):
        raise HTTPException(status_code=403, detail="Admin role required to update org defaults")

    # Load current rules, apply updates
    current_rules = await get_org_default_rules(org_id, db)
    updated = _apply_rule_updates(current_rules, update)

    success = await save_org_default_rules(org_id, updated, db)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to save rules")

    try:
        await db.commit()
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to commit org default rules: {e}")
        raise HTTPException(status_code=500, detail="Failed to save rules")

    return {
        "message": "Organization default rules updated",
        "rules": updated.dict(exclude={"lo_id"}),
    }


@router.get("/rules/{lo_id}")
async def get_lo_rules(
    lo_id: int,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """Get current scheduling rules for a specific loan officer."""
    user = await _get_current_user(request, db)
    org_id = getattr(user, "organization_id", None)

    rules = await get_rules_for_lo(lo_id, db, org_id)
    return {
        "rules": rules.dict(),
        "source": rules.source,
        "lo_id": lo_id,
        "org_id": org_id,
    }


@router.put("/rules/{lo_id}")
async def update_lo_rules(
    lo_id: int,
    update: RulesUpdateRequest,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """
    Update scheduling rules for a specific loan officer.
    LO can update their own rules; admins can update any LO's rules.
    """
    user = await _get_current_user(request, db)
    org_id = _get_org_id(user)
    user_id = getattr(user, "id", None)
    user_role = getattr(user, "role", None)

    # Authorization: own rules or admin
    is_admin = user_role in ("admin", "site_admin", "platform_admin", "super_admin")
    if user_id != lo_id and not is_admin:
        raise HTTPException(
            status_code=403,
            detail="You can only update your own scheduling rules"
        )

    # Load current rules, apply updates
    current_rules = await get_rules_for_lo(lo_id, db, org_id)
    updated = _apply_rule_updates(current_rules, update)

    success = await save_rules_for_lo(lo_id, org_id, updated, db)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to save rules")

    try:
        await db.commit()
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to commit LO rules: {e}")
        raise HTTPException(status_code=500, detail="Failed to save rules")

    return {
        "message": f"Scheduling rules updated for LO {lo_id}",
        "rules": updated.dict(),
    }


@router.post("/rules/validate")
async def validate_booking(
    body: ValidateBookingRequest,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """
    Validate a proposed booking against all scheduling rules (dry-run).

    Does not create an appointment. Returns whether the booking would be
    allowed and any rule violations found. If the proposed time is not valid,
    the response includes the next available slot.
    """
    user = await _get_current_user(request, db)
    org_id = getattr(user, "organization_id", None)

    # Load rules for the target LO
    rules = await get_rules_for_lo(body.lo_id, db, org_id)

    # Calculate proposed end
    proposed_end = body.proposed_start + timedelta(minutes=body.duration_minutes)

    # Run full validation
    is_valid, violations = await is_bookable(
        body.lo_id, body.proposed_start, proposed_end,
        rules, db, is_vip=body.is_vip,
    )

    # If not valid, find the next available slot
    next_avail = None
    if not is_valid:
        try:
            next_slot = await get_next_available(
                body.lo_id, body.proposed_start, body.duration_minutes,
                rules, db, max_search_days=14,
            )
            if next_slot:
                next_avail = next_slot.isoformat()
        except Exception as e:
            logger.debug(f"Could not find next available slot: {e}")

    return {
        "is_valid": is_valid,
        "violations": [v.dict() for v in violations],
        "rules_applied": {
            "source": rules.source,
            "buffer_before": rules.buffer_before_minutes,
            "buffer_after": rules.buffer_after_minutes,
            "min_notice_hours": rules.min_notice_hours,
            "max_advance_days": rules.max_advance_days,
            "max_daily": rules.max_appointments_per_day,
            "enforce_lunch": rules.enforce_lunch_break,
        },
        "next_available": next_avail,
    }


# ============================================================================
# HELPERS
# ============================================================================

def _apply_rule_updates(current: SchedulingRules, update: RulesUpdateRequest) -> SchedulingRules:
    """Apply partial updates to a SchedulingRules instance."""
    data = current.dict()

    for field_name, value in update.dict(exclude_unset=True).items():
        if value is not None:
            data[field_name] = value

    return SchedulingRules(**data)
