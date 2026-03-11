"""
Scheduler Blocked Times - CRUD endpoints for blocked time periods.

Extracted from routes/scheduler_appointment_routes.py

Endpoints:
  - GET    /blocked-times              List blocked time periods
  - POST   /blocked-times              Create a blocked time period
  - DELETE /blocked-times/{block_id}   Delete a blocked time period
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from datetime import datetime, date, time
from typing import Optional
import logging

from scheduler_models import BlockedTimeCreate

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


def get_db():
    if _get_db is None:
        raise RuntimeError("Dependencies not set")
    yield from _get_db()


async def get_current_user(request: Request, db: Session = Depends(get_db)):
    if _get_current_user_func is None:
        raise RuntimeError("Dependencies not set")
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else ""
    return await _get_current_user_func(token=token, request=request, db=db)


def _get_org_id(user) -> int:
    """Get organization_id from user, raise 403 if missing."""
    org_id = getattr(user, 'organization_id', None)
    if org_id is None:
        raise HTTPException(status_code=403, detail="No organization context")
    return org_id


def _is_scheduler_admin(user) -> bool:
    """
    Standardized admin check for scheduler endpoints.
    Uses permission_role (primary) with role fallback.
    Only true security roles qualify.
    """
    role = getattr(user, 'permission_role', '') or getattr(user, 'role', '') or ''
    return role.lower() in ('admin', 'site_admin', 'platform_admin')


def _audit_log(db, org_id: int, user_id: int, action: str, entity_type: str,
               entity_id: int = None, changes: dict = None, request: Request = None):
    """Record an audit log entry for scheduler operations."""
    AuditLog = _models.get('SchedulerAuditLog')
    if not AuditLog:
        return
    try:
        entry = AuditLog(
            organization_id=org_id,
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            changes=changes,
            ip_address=request.client.host if request and request.client else None,
            user_agent=str(request.headers.get('user-agent', ''))[:255] if request else None,
        )
        db.add(entry)
        # Don't commit here — let the caller's commit include this
    except Exception as e:
        logger.warning(f"Failed to write audit log: {e}")


# ============================================================================
# BLOCKED TIME ENDPOINTS
# ============================================================================

@router.get("/blocked-times")
async def list_blocked_times(
    request: Request,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    db: Session = Depends(get_db)
):
    """List blocked time periods"""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    BlockedTime = _models['BlockedTime']

    query = db.query(BlockedTime).filter(
        BlockedTime.is_active == True,
        BlockedTime.organization_id == org_id,
        or_(
            BlockedTime.user_id == user.id,
            and_(BlockedTime.applies_to_all_users == True, BlockedTime.organization_id == org_id)
        )
    )

    if start_date:
        query = query.filter(BlockedTime.end_datetime >= datetime.combine(start_date, time.min))

    if end_date:
        query = query.filter(BlockedTime.start_datetime <= datetime.combine(end_date, time.max))

    blocked = query.order_by(BlockedTime.start_datetime).all()

    return {
        "blocked_times": [
            {
                "id": b.id,
                "title": b.title,
                "description": b.description,
                "block_type": b.block_type,
                "start_datetime": b.start_datetime.isoformat(),
                "end_datetime": b.end_datetime.isoformat(),
                "all_day": b.all_day,
                "is_recurring": b.is_recurring,
                "recurrence_pattern": b.recurrence_pattern,
                "applies_to_all_users": b.applies_to_all_users
            }
            for b in blocked
        ]
    }


@router.post("/blocked-times")
async def create_blocked_time(
    block_data: BlockedTimeCreate,
    request: Request,
    db: Session = Depends(get_db)
):
    """Create a blocked time period"""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    BlockedTime = _models['BlockedTime']

    # H1: Only admins can set applies_to_all_users
    applies_to_all = False
    if block_data.applies_to_all_users:
        if _is_scheduler_admin(user):
            applies_to_all = True
        else:
            raise HTTPException(status_code=403, detail="Only admins can block time for all users")

    blocked = BlockedTime(
        organization_id=org_id,
        user_id=user.id,
        title=block_data.title,
        description=block_data.description,
        block_type=block_data.block_type,
        start_datetime=block_data.start_datetime,
        end_datetime=block_data.end_datetime,
        all_day=block_data.all_day,
        is_recurring=block_data.is_recurring,
        recurrence_pattern=block_data.recurrence_pattern,
        applies_to_all_users=applies_to_all,
        created_by_id=user.id
    )

    db.add(blocked)
    _audit_log(db, org_id, user.id, 'created', 'blocked_time',
               changes={'title': block_data.title, 'applies_to_all': applies_to_all}, request=request)
    db.commit()
    db.refresh(blocked)

    return {"message": "Blocked time created", "blocked_time_id": blocked.id}


@router.delete("/blocked-times/{block_id}")
async def delete_blocked_time(
    block_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """Delete a blocked time period"""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    BlockedTime = _models['BlockedTime']

    blocked = db.query(BlockedTime).filter(
        BlockedTime.id == block_id,
        BlockedTime.organization_id == org_id,
        BlockedTime.user_id == user.id
    ).first()

    if not blocked:
        raise HTTPException(status_code=404, detail="Blocked time not found")

    _audit_log(db, org_id, user.id, 'deleted', 'blocked_time',
               entity_id=block_id, changes={'title': blocked.title}, request=request)
    db.delete(blocked)
    db.commit()

    return {"message": "Blocked time deleted"}
