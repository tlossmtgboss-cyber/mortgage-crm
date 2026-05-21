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

from database import get_db
from auth.dependencies import get_current_user

logger = logging.getLogger(__name__)

# Explicit table creation for production (Base.metadata.create_all is skipped)
try:
    from database.models.followup_cadence import (
        FollowupCadence as _FC,
        FollowupExecution as _FE,
    )
    from db import engine as _engine
    _FC.__table__.create(_engine, checkfirst=True)
    _FE.__table__.create(_engine, checkfirst=True)
except Exception as _e:
    logger.warning("Could not create followup cadence tables: %s", _e)

router = APIRouter(prefix="/cadence", tags=["smart-docs-cadence"])


# ---------------------------------------------------------------------------
# Service helper
# ---------------------------------------------------------------------------

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


class PauseSequenceBody(BaseModel):
    reason: str = "Manual pause"


class CancelSequenceBody(BaseModel):
    reason: str = "lo_cancelled"


# ---------------------------------------------------------------------------
# Cadence Template CRUD
# ---------------------------------------------------------------------------

@router.get("/templates")
async def list_cadence_templates(
    trigger_type: Optional[str] = Query(None),
    include_system: bool = Query(True),
    active_only: bool = Query(True),
    db=Depends(get_db),
    current_user=Depends(get_current_user),
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
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    service = _get_service(db, current_user)
    result = await service.get_cadence(cadence_id)
    if not result:
        raise HTTPException(status_code=404, detail="Cadence not found")
    return result


@router.post("/templates")
async def create_cadence_template(
    body: CreateCadenceBody,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
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
    db=Depends(get_db),
    current_user=Depends(get_current_user),
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
    db=Depends(get_db),
    current_user=Depends(get_current_user),
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
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    service = _get_service(db, current_user)
    success = await service.deactivate_cadence(cadence_id)
    if not success:
        raise HTTPException(status_code=404, detail="Cadence not found or not editable")
    return {"cadence_id": cadence_id, "status": "deactivated"}


# ---------------------------------------------------------------------------
# Execution Management
# ---------------------------------------------------------------------------

@router.get("/executions")
async def list_executions(
    loan_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    service = _get_service(db, current_user)
    result = await service.get_active_executions(loan_id=loan_id, limit=limit)
    if status:
        result = [e for e in result if e.get("status") == status]
    return {"executions": result, "total": len(result)}


@router.get("/executions/{execution_id}/timeline")
async def get_execution_timeline(
    execution_id: int,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    service = _get_service(db, current_user)
    result = await service.get_execution_timeline(execution_id)
    if not result:
        raise HTTPException(status_code=404, detail="Execution not found")
    return result


@router.post("/executions/start")
async def start_cadence_execution(
    body: StartCadenceBody,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
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
    db=Depends(get_db),
    current_user=Depends(get_current_user),
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
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    service = _get_service(db, current_user)
    count = await service.pause_all_for_loan(loan_id, reason=body.reason)
    return {"loan_id": loan_id, "paused_count": count}


@router.post("/executions/loan/{loan_id}/resume")
async def resume_loan_executions(
    loan_id: int,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    service = _get_service(db, current_user)
    count = await service.resume_all_for_loan(loan_id)
    return {"loan_id": loan_id, "resumed_count": count}


@router.post("/executions/loan/{loan_id}/cancel")
async def cancel_loan_executions(
    loan_id: int,
    body: CancelExecutionBody,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    service = _get_service(db, current_user)
    count = await service.cancel_all_for_loan(loan_id, reason=body.reason)
    return {"loan_id": loan_id, "cancelled_count": count}


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------

@router.get("/analytics")
async def get_cadence_analytics(
    cadence_id: Optional[int] = Query(None),
    days: int = Query(30, ge=1, le=365),
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    service = _get_service(db, current_user)
    result = await service.get_cadence_analytics(cadence_id=cadence_id, days=days)
    return result


@router.post("/seed-defaults")
async def seed_system_cadences(
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    service = _get_service(db, current_user)
    count = await service.seed_system_cadences()
    return {"seeded": count, "message": f"Seeded {count} system cadence templates"}


# ===========================================================================
# Sequence-level endpoints (consumed by frontend client-file cadenceApi)
#
# The frontend calls:
#   POST /api/v1/cadence/sequences/{sequence_id}/pause
#   POST /api/v1/cadence/sequences/{sequence_id}/resume
#   POST /api/v1/cadence/sequences/{sequence_id}/cancel
#
# This router is mounted at /api/v1 in router_registry.py so the full
# paths resolve correctly.
# ===========================================================================

sequences_router = APIRouter(
    prefix="/cadence", tags=["cadence-sequences"],
)


def _serialize_execution(ex) -> dict:
    """Serialize a FollowupExecution to the shape the frontend expects."""
    return {
        "id": str(ex.id),
        "cadence_id": ex.cadence_id,
        "loan_id": ex.loan_id,
        "status": ex.status,
        "attempts_made": ex.attempts_made or 0,
        "max_attempts": None,  # lives on cadence template, not execution
        "current_step": ex.current_step,
        "next_send_at": ex.next_send_at.isoformat() if ex.next_send_at else None,
        "paused_at": ex.paused_at.isoformat() if ex.paused_at else None,
        "pause_reason": ex.pause_reason,
        "cancelled_at": ex.cancelled_at.isoformat() if ex.cancelled_at else None,
        "cancel_reason": ex.cancel_reason,
        "started_at": ex.created_at.isoformat() if ex.created_at else None,
        "ended_at": (
            (ex.completed_at or ex.cancelled_at).isoformat()
            if (ex.completed_at or ex.cancelled_at)
            else None
        ),
        "borrower_email": ex.borrower_email,
        "borrower_name": ex.borrower_name,
    }


def _get_execution_or_404(db, execution_id: int, org_id: int):
    """Look up a FollowupExecution by ID, scoped to org. Raises 404 if missing."""
    from database.models.followup_cadence import FollowupExecution

    execution = (
        db.query(FollowupExecution)
        .filter(
            FollowupExecution.id == execution_id,
            FollowupExecution.organization_id == org_id,
        )
        .first()
    )
    if not execution:
        raise HTTPException(status_code=404, detail="Cadence sequence not found")
    return execution


@sequences_router.post("/sequences/{sequence_id}/pause")
async def pause_sequence(
    sequence_id: int,
    body: PauseSequenceBody = None,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Pause a single cadence execution (sequence).

    Sets status to PAUSED and records the pause timestamp and reason.
    Only ACTIVE executions can be paused.
    """
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization context required")

    execution = _get_execution_or_404(db, sequence_id, org_id)

    if execution.status != "ACTIVE":
        raise HTTPException(
            status_code=409,
            detail=f"Cannot pause sequence with status '{execution.status}'; must be ACTIVE",
        )

    reason = body.reason if body else "Manual pause"

    execution.status = "PAUSED"
    execution.paused_at = datetime.utcnow()
    execution.pause_reason = reason
    execution.next_send_at = None
    db.commit()
    db.refresh(execution)

    logger.info("Paused cadence sequence %d for org %d: %s", sequence_id, org_id, reason)
    return _serialize_execution(execution)


@sequences_router.post("/sequences/{sequence_id}/resume")
async def resume_sequence(
    sequence_id: int,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Resume a paused cadence execution (sequence).

    Resets status to ACTIVE, clears pause fields, and schedules
    next_send_at to now so the scheduler picks it up promptly.
    """
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization context required")

    execution = _get_execution_or_404(db, sequence_id, org_id)

    if execution.status != "PAUSED":
        raise HTTPException(
            status_code=409,
            detail=f"Cannot resume sequence with status '{execution.status}'; must be PAUSED",
        )

    execution.status = "ACTIVE"
    execution.paused_at = None
    execution.pause_reason = None
    execution.next_send_at = datetime.utcnow()
    db.commit()
    db.refresh(execution)

    logger.info("Resumed cadence sequence %d for org %d", sequence_id, org_id)
    return _serialize_execution(execution)


@sequences_router.post("/sequences/{sequence_id}/cancel")
async def cancel_sequence(
    sequence_id: int,
    body: CancelSequenceBody = None,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Cancel a cadence execution (sequence).

    Sets status to CANCELLED and records the cancellation timestamp
    and reason. Both ACTIVE and PAUSED executions can be cancelled.
    """
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization context required")

    execution = _get_execution_or_404(db, sequence_id, org_id)

    if execution.status not in ("ACTIVE", "PAUSED"):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot cancel sequence with status '{execution.status}'; must be ACTIVE or PAUSED",
        )

    reason = body.reason if body else "lo_cancelled"

    execution.status = "CANCELLED"
    execution.cancelled_at = datetime.utcnow()
    execution.cancel_reason = reason
    execution.next_send_at = None
    db.commit()
    db.refresh(execution)

    logger.info("Cancelled cadence sequence %d for org %d: %s", sequence_id, org_id, reason)
    return _serialize_execution(execution)
