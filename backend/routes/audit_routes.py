"""
Calendar Audit Routes — Compliance-Grade Audit Trail API

Provides endpoints for querying the comprehensive calendar audit log:
- Entity-specific audit trails (appointment, booking link, etc.)
- User activity logs
- Search / filter audit entries
- Suspicious activity detection

URL prefix: /api/v1/scheduler/audit (applied by parent aggregator)

All endpoints require authentication and tenant-scope the results
to the caller's organization_id.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone
from typing import Optional
import logging

from services.calendar_audit_service import CalendarAuditService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/audit", tags=["scheduler-audit"])

# ---------------------------------------------------------------------------
# Dependency injection (same pattern as other scheduler sub-modules)
# ---------------------------------------------------------------------------
_get_db = None
_get_current_user_func = None
_models = None


def set_dependencies(get_db_func, get_current_user_func, models_dict):
    """Set dependencies from parent module."""
    global _get_db, _get_current_user_func, _models
    _get_db = get_db_func
    _get_current_user_func = get_current_user_func
    _models = models_dict

    # Initialize the audit service with the CalendarAuditLog model
    cal_audit_model = models_dict.get("CalendarAuditLog")
    if cal_audit_model:
        CalendarAuditService.init(cal_audit_model)
    else:
        logger.warning("CalendarAuditLog model not found in models_dict — audit routes will be non-functional")


from db import get_async_db


from auth.dependencies import get_current_user  # dedup: was local wrapper
def _get_org_id(user) -> int:
    """Get organization_id from user, raise 403 if missing."""
    org_id = getattr(user, "organization_id", None)
    if org_id is None:
        raise HTTPException(status_code=403, detail="No organization context")
    return org_id


def _is_scheduler_admin(user) -> bool:
    """Check if user has scheduler admin permissions."""
    role = getattr(user, "permission_role", None) or getattr(user, "role", None) or ""
    return role.lower() in ("admin", "platform_admin", "site_admin", "super_admin")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/appointment/{appointment_id}")
async def get_appointment_audit_trail(
    appointment_id: int,
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(get_current_user),
):
    """Get the complete audit trail for a specific appointment.

    Returns all audit log entries related to the given appointment,
    ordered by most recent first.
    """
    org_id = _get_org_id(current_user)

    try:
        entries = await CalendarAuditService.get_entity_history(
            db=db,
            entity_type="appointment",
            entity_id=str(appointment_id),
            organization_id=org_id,
            limit=limit,
            offset=offset,
        )
        return {
            "appointment_id": appointment_id,
            "entries": entries,
            "count": len(entries),
            "limit": limit,
            "offset": offset,
        }
    except RuntimeError as e:
        logger.warning(f"Audit service not initialized: {e}")
        raise HTTPException(status_code=503, detail="Audit service not available")
    except Exception as e:
        logger.exception(f"Failed to retrieve appointment audit trail: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve audit trail")


@router.get("/user/{user_id}")
async def get_user_activity_log(
    user_id: int,
    request: Request,
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(get_current_user),
):
    """Get a user's calendar activity log.

    Shows all scheduler-related actions performed by the specified user.
    Non-admin users can only view their own activity.
    """
    org_id = _get_org_id(current_user)
    current_user_id = getattr(current_user, "id", None)

    # Non-admin users can only view their own activity
    if not _is_scheduler_admin(current_user) and current_user_id != user_id:
        raise HTTPException(
            status_code=403,
            detail="You can only view your own activity log",
        )

    try:
        entries = await CalendarAuditService.get_user_activity(
            db=db,
            user_id=str(user_id),
            organization_id=org_id,
            days=days,
            limit=limit,
            offset=offset,
        )
        return {
            "user_id": user_id,
            "period_days": days,
            "entries": entries,
            "count": len(entries),
            "limit": limit,
            "offset": offset,
        }
    except RuntimeError as e:
        logger.warning(f"Audit service not initialized: {e}")
        raise HTTPException(status_code=503, detail="Audit service not available")
    except Exception as e:
        logger.exception(f"Failed to retrieve user activity log: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve activity log")


@router.get("/search")
async def search_audit_logs(
    request: Request,
    event_type: Optional[str] = Query(None, description="Filter by event type, e.g. appointment.created"),
    event_category: Optional[str] = Query(None, description="Filter by category: booking, modification, settings, export, compliance"),
    severity: Optional[str] = Query(None, description="Filter by severity: info, warning, critical"),
    actor_id: Optional[str] = Query(None, description="Filter by actor ID"),
    actor_type: Optional[str] = Query(None, description="Filter by actor type: user, system, ai_agent, webhook, public"),
    entity_type: Optional[str] = Query(None, description="Filter by entity type: appointment, booking_link, blocked_time, config"),
    entity_id: Optional[str] = Query(None, description="Filter by entity ID"),
    start_date: Optional[str] = Query(None, description="Start date (ISO 8601)"),
    end_date: Optional[str] = Query(None, description="End date (ISO 8601)"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(get_current_user),
):
    """Search audit logs with multiple filter criteria.

    Supports filtering by event type, category, severity, actor, entity,
    and date range. Results are tenant-scoped to the caller's organization.
    """
    org_id = _get_org_id(current_user)

    # Parse optional date filters
    parsed_start = None
    parsed_end = None
    if start_date:
        try:
            parsed_start = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid start_date format. Use ISO 8601.")
    if end_date:
        try:
            parsed_end = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid end_date format. Use ISO 8601.")

    # Validate enum-like parameters
    valid_severities = {"info", "warning", "critical"}
    if severity and severity not in valid_severities:
        raise HTTPException(status_code=400, detail=f"Invalid severity. Must be one of: {', '.join(valid_severities)}")

    valid_actor_types = {"user", "system", "ai_agent", "webhook", "public"}
    if actor_type and actor_type not in valid_actor_types:
        raise HTTPException(status_code=400, detail=f"Invalid actor_type. Must be one of: {', '.join(valid_actor_types)}")

    valid_categories = {"booking", "modification", "access", "settings", "export", "compliance", "other"}
    if event_category and event_category not in valid_categories:
        raise HTTPException(status_code=400, detail=f"Invalid event_category. Must be one of: {', '.join(valid_categories)}")

    try:
        result = await CalendarAuditService.search_audit_logs(
            db=db,
            organization_id=org_id,
            event_type=event_type,
            event_category=event_category,
            severity=severity,
            actor_id=actor_id,
            actor_type=actor_type,
            entity_type=entity_type,
            entity_id=entity_id,
            start_date=parsed_start,
            end_date=parsed_end,
            limit=limit,
            offset=offset,
        )
        return result
    except RuntimeError as e:
        logger.warning(f"Audit service not initialized: {e}")
        raise HTTPException(status_code=503, detail="Audit service not available")
    except Exception as e:
        logger.exception(f"Failed to search audit logs: {e}")
        raise HTTPException(status_code=500, detail="Failed to search audit logs")


@router.get("/suspicious")
async def get_suspicious_activity(
    request: Request,
    days: int = Query(7, ge=1, le=90),
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(get_current_user),
):
    """Detect suspicious activity patterns in the calendar audit log.

    Checks for:
    - Mass cancellations by a single actor
    - Off-hours access (operations between 10 PM and 6 AM UTC)
    - Unusual actor types performing sensitive operations
    - Critical severity event clusters

    Admin-only endpoint.
    """
    org_id = _get_org_id(current_user)

    if not _is_scheduler_admin(current_user):
        raise HTTPException(
            status_code=403,
            detail="Only administrators can view suspicious activity reports",
        )

    try:
        findings = await CalendarAuditService.get_suspicious_activity(
            db=db,
            organization_id=org_id,
            days=days,
        )
        return findings
    except RuntimeError as e:
        logger.warning(f"Audit service not initialized: {e}")
        raise HTTPException(status_code=503, detail="Audit service not available")
    except Exception as e:
        logger.exception(f"Failed to generate suspicious activity report: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate report")


@router.get("/stats")
async def get_audit_stats(
    request: Request,
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(get_current_user),
):
    """Get aggregate audit statistics for the organization.

    Returns event counts broken down by event type, severity, and actor type.
    """
    org_id = _get_org_id(current_user)

    try:
        stats = await CalendarAuditService.get_audit_stats(
            db=db,
            organization_id=org_id,
            days=days,
        )
        return stats
    except RuntimeError as e:
        logger.warning(f"Audit service not initialized: {e}")
        raise HTTPException(status_code=503, detail="Audit service not available")
    except Exception as e:
        logger.exception(f"Failed to generate audit stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate stats")


@router.get("/entity/{entity_type}/{entity_id}")
async def get_entity_audit_trail(
    entity_type: str,
    entity_id: str,
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(get_current_user),
):
    """Get audit trail for any entity type (appointment, booking_link, config, etc.).

    More general than the appointment-specific endpoint.
    """
    org_id = _get_org_id(current_user)

    valid_entity_types = {
        "appointment", "booking_link", "blocked_time", "config",
        "availability", "appointment_type", "routing_rule",
    }
    if entity_type not in valid_entity_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid entity_type. Must be one of: {', '.join(sorted(valid_entity_types))}",
        )

    try:
        entries = await CalendarAuditService.get_entity_history(
            db=db,
            entity_type=entity_type,
            entity_id=entity_id,
            organization_id=org_id,
            limit=limit,
            offset=offset,
        )
        return {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "entries": entries,
            "count": len(entries),
            "limit": limit,
            "offset": offset,
        }
    except RuntimeError as e:
        logger.warning(f"Audit service not initialized: {e}")
        raise HTTPException(status_code=503, detail="Audit service not available")
    except Exception as e:
        logger.exception(f"Failed to retrieve entity audit trail: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve audit trail")
