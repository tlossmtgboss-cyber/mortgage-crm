"""
Smart Docs Cadence Management API Routes

Exposes the SmartCadenceService for cadence template CRUD,
execution monitoring, and analytics.

Mounted at: /api/smart-docs/cadence/*
"""

import logging
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cadence", tags=["smart-docs-cadence"])

# ---------------------------------------------------------------------------
# Dependency helpers (lazily resolved to avoid circular imports)
# ---------------------------------------------------------------------------
_get_db = None
_get_current_user = None


def _ensure_deps():
    global _get_db, _get_current_user
    if _get_db is None:
        from db import get_db as db_dep
        _get_db = db_dep
    if _get_current_user is None:
        try:
            from auth.dependencies import get_current_user as auth_dep
            _get_current_user = auth_dep
        except Exception:
            from main import get_current_user as auth_dep
            _get_current_user = auth_dep


def _db():
    _ensure_deps()
    return Depends(_get_db)


def _user():
    _ensure_deps()
    return Depends(_get_current_user)


def _get_service(db, user):
    from services.smart_docs.smart_cadence_service import get_smart_cadence_service
    org_id = getattr(user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization context required")
    return get_smart_cadence_service(db, org_id)


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class ChannelStep(BaseModel):
    day: int = Field(..., ge=0, description="Day offset from cadence start")
    channel: str = Field(..., description="email | sms | call | escalate | portal | in_app")
    template: str = Field(..., description="Template slug")
    ab_variant: Optional[str] = Field(None, description="A or B for A/B testing")


class CreateCadenceBody(BaseModel):
    cadence_name: str = Field(..., min_length=1, max_length=200)
    trigger_type: str = Field(..., description="DOC_REQUESTED | DOC_OVERDUE | DOC_EXPIRING | CONDITION_ADDED | DOC_REJECTED | MANUAL")
    channel_sequence: List[ChannelStep]
    description: Optional[str] = None
    max_attempts: int = Field(5, ge=1, le=20)
    escalation_after: int = Field(3, ge=1, le=20)
    quiet_hours_start: int = Field(20, ge=0, le=23)
    quiet_hours_end: int = Field(8, ge=0, le=23)
    weekend_enabled: bool = False
    holiday_aware: bool = True
    ab_test_enabled: bool = False
    ab_test_name: Optional[str] = None
    ab_test_split_pct: float = Field(50.0, ge=0, le=100)


class UpdateCadenceBody(BaseModel):
    cadence_name: Optional[str] = None
    description: Optional[str] = None
    channel_sequence: Optional[List[ChannelStep]] = None
    max_attempts: Optional[int] = None
    escalation_after: Optional[int] = None
    quiet_hours_start: Optional[int] = None
    quiet_hours_end: Optional[int] = None
    weekend_enabled: Optional[bool] = None
    holiday_aware: Optional[bool] = None
    is_active: Optional[bool] = None
    ab_test_enabled: Optional[bool] = None
    ab_test_name: Optional[str] = None
    ab_test_split_pct: Optional[float] = None


class StartCadenceBody(BaseModel):
    cadence_id: int
    loan_id: int
    borrower_email: Optional[str] = None
    borrower_phone: Optional[str] = None
    borrower_name: Optional[str] = None
    document_request_id: Optional[int] = None


class CancelExecutionBody(BaseModel):
    reason: str = "Manual cancellation"


class PauseLoanBody(BaseModel):
    reason: str = "Manual pause"


# ---------------------------------------------------------------------------
# Cadence Template CRUD
# ---------------------------------------------------------------------------

@router.get("/templates")
async def list_cadences(
    trigger_type: Optional[str] = Query(None),
    include_system: bool = Query(True),
    active_only: bool = Query(True),
    db=Depends(lambda: None),
    current_user=Depends(lambda: None),
):
    _ensure_deps()
    from db import get_db
    from services.smart_docs.smart_cadence_service import get_smart_cadence_service

    db_gen = get_db()
    db_session = next(db_gen)
    try:
        user_dep = _get_current_user
        # Re-resolve with real DI - use simpler approach
        org_id = getattr(current_user, "organization_id", None)
        service = get_smart_cadence_service(db_session, org_id or 0)
        result = await service.list_cadences(
            trigger_type=trigger_type,
            include_system=include_system,
            active_only=active_only,
        )
        return {"cadences": result, "total": len(result)}
    finally:
        try:
            next(db_gen, None)
        except Exception:
            pass


# Use proper FastAPI dependency injection pattern
@router.get("/templates", name="list_cadence_templates")
async def list_cadence_templates_endpoint():
    """Placeholder - actual handler below uses proper DI."""
    pass


# Remove the placeholder and use a cleaner pattern
router.routes.clear()


# Re-define all routes with proper dependency injection
def _register_routes():
    """Register all cadence routes with proper dependency injection."""
    _ensure_deps()

    @router.get("/templates")
    async def list_cadence_templates(
        trigger_type: Optional[str] = Query(None),
        include_system: bool = Query(True),
        active_only: bool = Query(True),
        db=Depends(_get_db),
        current_user=Depends(_get_current_user),
    ):
        service = _get_service(db, current_user)
        result = await service.list_cadences(
            trigger_type=trigger_type,
            include_system=include_system,
            active_only=active_only,
        )
        return {"cadences": result, "total": len(result)}

    @router.get("/templates/{cadence_id}")
    async def get_cadence_template(
        cadence_id: int,
        db=Depends(_get_db),
        current_user=Depends(_get_current_user),
    ):
        service = _get_service(db, current_user)
        result = await service.get_cadence(cadence_id)
        if not result:
            raise HTTPException(status_code=404, detail="Cadence not found")
        return result

    @router.post("/templates")
    async def create_cadence_template(
        body: CreateCadenceBody,
        db=Depends(_get_db),
        current_user=Depends(_get_current_user),
    ):
        service = _get_service(db, current_user)
        try:
            result = await service.create_cadence(
                cadence_name=body.cadence_name,
                trigger_type=body.trigger_type,
                channel_sequence=[s.dict() for s in body.channel_sequence],
                max_attempts=body.max_attempts,
                escalation_after=body.escalation_after,
                quiet_hours_start=body.quiet_hours_start,
                quiet_hours_end=body.quiet_hours_end,
                weekend_enabled=body.weekend_enabled,
                holiday_aware=body.holiday_aware,
                description=body.description,
                created_by_user_id=getattr(current_user, "id", None),
            )
            return result
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))

    @router.put("/templates/{cadence_id}")
    async def update_cadence_template(
        cadence_id: int,
        body: UpdateCadenceBody,
        db=Depends(_get_db),
        current_user=Depends(_get_current_user),
    ):
        service = _get_service(db, current_user)
        updates = body.dict(exclude_unset=True)
        if "channel_sequence" in updates and updates["channel_sequence"] is not None:
            updates["channel_sequence"] = [
                s.dict() if hasattr(s, "dict") else s
                for s in updates["channel_sequence"]
            ]
        result = await service.update_cadence(cadence_id, **updates)
        if not result:
            raise HTTPException(status_code=404, detail="Cadence not found or not editable")
        return result

    @router.post("/templates/{cadence_id}/clone")
    async def clone_system_cadence(
        cadence_id: int,
        new_name: Optional[str] = Query(None),
        db=Depends(_get_db),
        current_user=Depends(_get_current_user),
    ):
        service = _get_service(db, current_user)
        result = await service.clone_system_cadence(
            system_cadence_id=cadence_id,
            new_name=new_name,
            created_by_user_id=getattr(current_user, "id", None),
        )
        if not result:
            raise HTTPException(status_code=404, detail="System cadence not found")
        return result

    @router.delete("/templates/{cadence_id}")
    async def deactivate_cadence_template(
        cadence_id: int,
        db=Depends(_get_db),
        current_user=Depends(_get_current_user),
    ):
        service = _get_service(db, current_user)
        success = await service.deactivate_cadence(cadence_id)
        if not success:
            raise HTTPException(status_code=404, detail="Cadence not found or not editable")
        return {"cadence_id": cadence_id, "status": "deactivated"}

    # -----------------------------------------------------------------------
    # Execution Management
    # -----------------------------------------------------------------------

    @router.get("/executions")
    async def list_executions(
        loan_id: Optional[int] = Query(None),
        status: Optional[str] = Query(None),
        limit: int = Query(50, ge=1, le=200),
        db=Depends(_get_db),
        current_user=Depends(_get_current_user),
    ):
        service = _get_service(db, current_user)
        result = await service.get_active_executions(loan_id=loan_id, limit=limit)
        if status:
            result = [e for e in result if e.get("status") == status]
        return {"executions": result, "total": len(result)}

    @router.get("/executions/{execution_id}/timeline")
    async def get_execution_timeline(
        execution_id: int,
        db=Depends(_get_db),
        current_user=Depends(_get_current_user),
    ):
        service = _get_service(db, current_user)
        result = await service.get_execution_timeline(execution_id)
        if not result:
            raise HTTPException(status_code=404, detail="Execution not found")
        return result

    @router.post("/executions/start")
    async def start_cadence_execution(
        body: StartCadenceBody,
        db=Depends(_get_db),
        current_user=Depends(_get_current_user),
    ):
        service = _get_service(db, current_user)
        try:
            result = await service.start_cadence(
                cadence_id=body.cadence_id,
                loan_id=body.loan_id,
                borrower_email=body.borrower_email,
                borrower_phone=body.borrower_phone,
                borrower_name=body.borrower_name,
                document_request_id=body.document_request_id,
            )
            return result
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))

    @router.post("/executions/{execution_id}/cancel")
    async def cancel_execution(
        execution_id: int,
        body: CancelExecutionBody,
        db=Depends(_get_db),
        current_user=Depends(_get_current_user),
    ):
        service = _get_service(db, current_user)
        success = await service.cancel_execution(execution_id, reason=body.reason)
        if not success:
            raise HTTPException(status_code=404, detail="Execution not found or already completed")
        return {"execution_id": execution_id, "status": "cancelled"}

    @router.post("/executions/loan/{loan_id}/pause")
    async def pause_loan_executions(
        loan_id: int,
        body: PauseLoanBody,
        db=Depends(_get_db),
        current_user=Depends(_get_current_user),
    ):
        service = _get_service(db, current_user)
        count = await service.pause_all_for_loan(loan_id, reason=body.reason)
        return {"loan_id": loan_id, "paused_count": count}

    @router.post("/executions/loan/{loan_id}/resume")
    async def resume_loan_executions(
        loan_id: int,
        db=Depends(_get_db),
        current_user=Depends(_get_current_user),
    ):
        service = _get_service(db, current_user)
        count = await service.resume_all_for_loan(loan_id)
        return {"loan_id": loan_id, "resumed_count": count}

    @router.post("/executions/loan/{loan_id}/cancel")
    async def cancel_loan_executions(
        loan_id: int,
        body: CancelExecutionBody,
        db=Depends(_get_db),
        current_user=Depends(_get_current_user),
    ):
        service = _get_service(db, current_user)
        count = await service.cancel_all_for_loan(loan_id, reason=body.reason)
        return {"loan_id": loan_id, "cancelled_count": count}

    # -----------------------------------------------------------------------
    # Analytics
    # -----------------------------------------------------------------------

    @router.get("/analytics")
    async def get_cadence_analytics(
        cadence_id: Optional[int] = Query(None),
        days: int = Query(30, ge=1, le=365),
        db=Depends(_get_db),
        current_user=Depends(_get_current_user),
    ):
        service = _get_service(db, current_user)
        result = await service.get_cadence_analytics(cadence_id=cadence_id, days=days)
        return result

    @router.post("/seed-defaults")
    async def seed_system_cadences(
        db=Depends(_get_db),
        current_user=Depends(_get_current_user),
    ):
        service = _get_service(db, current_user)
        count = await service.seed_system_cadences()
        return {"seeded": count, "message": f"Seeded {count} system cadence templates"}


# Register routes on module load
try:
    _register_routes()
except Exception as e:
    logger.warning(f"Cadence routes deferred: {e}")
