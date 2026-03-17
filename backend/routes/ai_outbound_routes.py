"""
AI Outbound Call Scheduler - API Routes

Endpoints for managing AI-driven outbound calls that schedule appointments
for leads, active clients, and MUM (past clients).

Prefix: /api/v1/ai-outbound
"""

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from database import get_db

import logging

logger = logging.getLogger(__name__)


# =============================================================================
# Auth dependency (lazy import to avoid circular imports)
# =============================================================================

def _get_auth():
    """Lazy import auth dependency."""
    from auth.dependencies import get_current_user_flexible
    return get_current_user_flexible


router = APIRouter(
    prefix="/api/v1/ai-outbound",
    tags=["AI Outbound Calls"],
)


# =============================================================================
# Pydantic Models
# =============================================================================

class QueueCallRequest(BaseModel):
    """Request to queue a single outbound call."""
    contact_id: int = Field(..., description="ID of the lead, loan, or mum_client")
    entity_type: str = Field(..., description="One of: lead, loan, mum_client")
    purpose: Optional[str] = Field(None, description="Reason for the call")
    script_variant: str = Field("default", description="Script template variant")
    priority: Optional[int] = Field(None, description="Priority override (1=urgent, 5=background)")


class BulkQueueRequest(BaseModel):
    """Request to queue calls for a segment."""
    segment: str = Field(
        ...,
        description="Segment: new_leads, stale_leads, active_pipeline, mum_due, refi_opportunity"
    )
    limit: int = Field(50, ge=1, le=500, description="Max contacts to queue")
    purpose: Optional[str] = Field(None, description="Purpose override")
    script_variant: str = Field("default", description="Script variant for all calls")


class CallOutcomeRequest(BaseModel):
    """Request to record a call outcome."""
    call_id: str = Field(..., description="The queued call ID")
    outcome: str = Field(
        ...,
        description="Outcome: connected, voicemail, no_answer, busy, failed, "
                     "appointment_scheduled, appointment_declined, callback_requested, not_interested"
    )
    appointment_id: Optional[int] = Field(None, description="Appointment ID if one was booked")
    notes: Optional[str] = Field(None, description="Call notes or transcript summary")
    call_duration_seconds: Optional[int] = Field(None, description="Call duration")


class UpdateSettingsRequest(BaseModel):
    """Request to update outbound scheduler settings."""
    enabled: Optional[bool] = None
    max_calls_per_lo_per_day: Optional[int] = Field(None, ge=1, le=200)
    calling_hours_start: Optional[str] = Field(None, description="HH:MM format")
    calling_hours_end: Optional[str] = Field(None, description="HH:MM format")
    retry_intervals_hours: Optional[List[int]] = None
    max_retries: Optional[int] = Field(None, ge=0, le=10)
    speed_to_lead_enabled: Optional[bool] = None
    speed_to_lead_sla_minutes: Optional[int] = Field(None, ge=1, le=60)
    auto_queue_new_leads: Optional[bool] = None
    auto_queue_mum_reviews: Optional[bool] = None
    preferred_script_variants: Optional[dict] = None


class QueueCallResponse(BaseModel):
    """Response after queuing a call."""
    success: bool
    call_id: Optional[str] = None
    priority: Optional[str] = None
    caller_type: Optional[str] = None
    contact_name: Optional[str] = None
    scheduled_for: Optional[str] = None
    error: Optional[str] = None


# =============================================================================
# Table initialization (runs once on first request)
# =============================================================================

_tables_initialized = False


def _ensure_tables(db: Session):
    """Ensure outbound tables exist (idempotent)."""
    global _tables_initialized
    if _tables_initialized:
        return
    try:
        from services.ai_outbound_scheduler import ensure_outbound_tables
        ensure_outbound_tables(db)
        _tables_initialized = True
    except Exception as e:
        logger.warning(f"Table initialization note: {e}")


# =============================================================================
# Endpoints
# =============================================================================

@router.post("/queue-call", response_model=QueueCallResponse)
async def queue_call(
    data: QueueCallRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Queue a single outbound AI call to a lead, loan borrower, or MUM client.

    The system will:
    1. Classify the contact (new_lead / active_client / mum)
    2. Run compliance checks (DNC, TCPA consent, calling hours)
    3. Calculate priority based on lead score and context
    4. Add to the call queue for processing
    """
    import main
    current_user = await main.get_current_user_flexible(request, db)

    _ensure_tables(db)

    from services.ai_outbound_scheduler import AIOutboundScheduler, CallPriority

    scheduler = AIOutboundScheduler(db)

    priority_override = None
    if data.priority is not None:
        try:
            priority_override = CallPriority(data.priority)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid priority: {data.priority}. Must be 1-5."
            )

    result = await scheduler.schedule_outbound_call(
        contact_id=data.contact_id,
        entity_type=data.entity_type,
        lo_id=current_user.id,
        purpose=data.purpose or "",
        script_variant=data.script_variant,
        priority_override=priority_override,
    )

    if not result.get("success"):
        return QueueCallResponse(
            success=False,
            error=result.get("error", "Unknown error"),
        )

    return QueueCallResponse(
        success=True,
        call_id=result.get("call_id"),
        priority=result.get("priority"),
        caller_type=result.get("caller_type"),
        contact_name=result.get("contact_name"),
        scheduled_for=result.get("scheduled_for"),
    )


@router.get("/queue")
async def get_call_queue(
    request: Request,
    status: Optional[str] = Query(None, description="Filter by status: pending, in_progress, completed, retry_scheduled"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """
    View the pending outbound call queue.

    Returns calls sorted by priority (urgent first) then scheduled time.
    """
    import main
    current_user = await main.get_current_user_flexible(request, db)

    _ensure_tables(db)

    params = {"lo_id": current_user.id, "limit": limit, "offset": offset}
    status_filter = ""
    if status:
        status_filter = "AND status = :status"
        params["status"] = status

    try:
        rows = db.execute(text(f"""
            SELECT
                call_id, contact_id, entity_type, contact_name,
                caller_type, priority, purpose, status, outcome,
                retry_count, max_retries, scheduled_for,
                vapi_call_id, appointment_id, created_at,
                last_attempt_at, completed_at, call_duration_seconds
            FROM ai_outbound_calls
            WHERE lo_id = :lo_id {status_filter}
            ORDER BY
                CASE status
                    WHEN 'in_progress' THEN 0
                    WHEN 'pending' THEN 1
                    WHEN 'retry_scheduled' THEN 2
                    ELSE 3
                END,
                priority ASC,
                scheduled_for ASC NULLS FIRST
            LIMIT :limit OFFSET :offset
        """), params).fetchall()

        total_result = db.execute(text(f"""
            SELECT COUNT(*) FROM ai_outbound_calls
            WHERE lo_id = :lo_id {status_filter}
        """), params).fetchone()

        calls = []
        for row in rows:
            calls.append({
                "call_id": row[0],
                "contact_id": row[1],
                "entity_type": row[2],
                "contact_name": row[3],
                "caller_type": row[4],
                "priority": row[5],
                "purpose": row[6],
                "status": row[7],
                "outcome": row[8],
                "retry_count": row[9],
                "max_retries": row[10],
                "scheduled_for": row[11].isoformat() if row[11] else None,
                "vapi_call_id": row[12],
                "appointment_id": row[13],
                "created_at": row[14].isoformat() if row[14] else None,
                "last_attempt_at": row[15].isoformat() if row[15] else None,
                "completed_at": row[16].isoformat() if row[16] else None,
                "call_duration_seconds": row[17],
            })

        return {
            "calls": calls,
            "total": total_result[0] if total_result else 0,
            "limit": limit,
            "offset": offset,
        }

    except Exception as e:
        logger.error(f"Error fetching call queue: {e}")
        return {"calls": [], "total": 0, "error": "Internal server error"}


@router.get("/stats")
async def get_conversion_stats(
    request: Request,
    days: int = Query(30, ge=1, le=365, description="Lookback period in days"),
    db: Session = Depends(get_db),
):
    """
    Get outbound call conversion statistics.

    Returns:
    - Overall call volumes and outcomes
    - Connection rate (% of calls that connect to a human)
    - Conversion rate (% of calls that result in a scheduled appointment)
    - Breakdown by caller type (new_lead, active_client, mum)
    - Best times of day for connecting
    """
    import main
    current_user = await main.get_current_user_flexible(request, db)

    _ensure_tables(db)

    from services.ai_outbound_scheduler import AIOutboundScheduler

    scheduler = AIOutboundScheduler(db)
    stats = await scheduler.get_conversion_stats(
        lo_id=current_user.id,
        days=days,
    )

    return {
        "period_days": days,
        "total_calls": stats.total_calls,
        "connected": stats.connected,
        "voicemails": stats.voicemails,
        "no_answers": stats.no_answers,
        "appointments_scheduled": stats.appointments_scheduled,
        "callbacks_requested": stats.callbacks_requested,
        "not_interested": stats.not_interested,
        "connection_rate": stats.connection_rate,
        "conversion_rate": stats.conversion_rate,
        "avg_calls_to_appointment": stats.avg_calls_to_appointment,
        "by_caller_type": stats.by_caller_type,
        "by_time_of_day": stats.by_time_of_day,
    }


@router.post("/bulk-queue")
async def bulk_queue_calls(
    data: BulkQueueRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Queue outbound calls for an entire segment.

    Segments:
    - **new_leads**: Leads created in last 24 hours with no contact yet
    - **stale_leads**: Leads with no contact in 7+ days
    - **active_pipeline**: Loans in active stages needing check-in (5+ days in stage)
    - **mum_due**: MUM clients not contacted in 90+ days
    - **refi_opportunity**: MUM clients with refinance opportunities
    """
    import main
    current_user = await main.get_current_user_flexible(request, db)

    _ensure_tables(db)

    valid_segments = {"new_leads", "stale_leads", "active_pipeline", "mum_due", "refi_opportunity"}
    if data.segment not in valid_segments:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid segment '{data.segment}'. Must be one of: {', '.join(sorted(valid_segments))}",
        )

    from services.ai_outbound_scheduler import AIOutboundScheduler

    scheduler = AIOutboundScheduler(db)
    result = await scheduler.bulk_queue_segment(
        segment=data.segment,
        lo_id=current_user.id,
        organization_id=getattr(current_user, "organization_id", None),
        limit=data.limit,
        purpose=data.purpose or "",
        script_variant=data.script_variant,
    )

    return result


@router.post("/outcome")
async def record_call_outcome(
    data: CallOutcomeRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Record the outcome of a completed outbound call.

    Called by the Vapi webhook handler or manually after a call completes.
    If the outcome is no_answer, voicemail, or busy, the system will
    automatically schedule a retry (up to max_retries).
    """
    import main
    current_user = await main.get_current_user_flexible(request, db)

    _ensure_tables(db)

    from services.ai_outbound_scheduler import AIOutboundScheduler, CallOutcome

    # Validate outcome
    try:
        outcome = CallOutcome(data.outcome)
    except ValueError:
        valid = [o.value for o in CallOutcome]
        raise HTTPException(
            status_code=400,
            detail=f"Invalid outcome '{data.outcome}'. Must be one of: {', '.join(valid)}",
        )

    scheduler = AIOutboundScheduler(db)
    result = await scheduler.handle_call_outcome(
        call_id=data.call_id,
        outcome=outcome,
        appointment_id=data.appointment_id,
        notes=data.notes,
        call_duration_seconds=data.call_duration_seconds,
    )

    return result


@router.put("/settings")
async def update_settings(
    data: UpdateSettingsRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Configure outbound call scheduler settings for your organization.

    Settings include:
    - **enabled**: Master on/off switch
    - **max_calls_per_lo_per_day**: Daily call limit per LO (default: 50)
    - **calling_hours_start/end**: Call window in HH:MM format
    - **retry_intervals_hours**: Hours between retry attempts (e.g., [2, 24, 72])
    - **max_retries**: Maximum retry attempts per contact
    - **speed_to_lead_enabled**: Auto-call new leads within SLA
    - **speed_to_lead_sla_minutes**: Speed-to-lead SLA in minutes (default: 5)
    - **auto_queue_new_leads**: Automatically queue new leads for calls
    - **auto_queue_mum_reviews**: Automatically queue MUM clients due for review
    - **preferred_script_variants**: Default script variant per caller type
    """
    import main
    current_user = await main.get_current_user_flexible(request, db)

    _ensure_tables(db)

    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=400, detail="User has no organization")

    # Validate calling hours format
    for field_name in ("calling_hours_start", "calling_hours_end"):
        val = getattr(data, field_name, None)
        if val:
            try:
                parts = val.split(":")
                h, m = int(parts[0]), int(parts[1])
                if not (0 <= h <= 23 and 0 <= m <= 59):
                    raise ValueError
            except (ValueError, IndexError):
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid {field_name} format. Use HH:MM (e.g., '08:00')",
                )

    from services.ai_outbound_scheduler import AIOutboundScheduler

    scheduler = AIOutboundScheduler(db)

    settings_dict = data.model_dump(exclude_none=True)
    result = await scheduler.update_settings(org_id, settings_dict)

    return result


@router.get("/settings")
async def get_settings(
    request: Request,
    db: Session = Depends(get_db),
):
    """Get current outbound scheduler settings."""
    import main
    current_user = await main.get_current_user_flexible(request, db)

    _ensure_tables(db)

    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        return {"settings": {}, "error": "User has no organization"}

    from services.ai_outbound_scheduler import AIOutboundScheduler

    scheduler = AIOutboundScheduler(db)
    settings = await scheduler.get_settings(org_id)

    return {"settings": settings}


@router.get("/scripts")
async def get_script_variants(
    caller_type: str = Query("new_lead", description="Caller type: new_lead, active_client, mum"),
):
    """
    Get available script variants for a caller type.

    Each variant has a different tone and approach:
    - **default**: Standard professional approach
    - **warm**: Relationship-focused, casual tone
    - **direct**: Concise, value-first approach
    - **milestone**: Celebration of loan progress (active clients)
    - **refi**: Refinance opportunity focused (MUM)
    - **referral**: Referral request focused (MUM)
    """
    from services.ai_call_scripts import CallScriptEngine

    engine = CallScriptEngine()
    variants = engine.get_available_variants(caller_type)

    return {
        "caller_type": caller_type,
        "variants": variants,
    }


@router.post("/process-queue")
async def process_queue(
    request: Request,
    max_calls: int = Query(10, ge=1, le=50, description="Max calls to process"),
    db: Session = Depends(get_db),
):
    """
    Process pending calls in the queue.

    This endpoint is typically called by a background task/cron job,
    but can also be triggered manually. It will:
    1. Load pending calls from the database
    2. Check compliance and calling hours for each
    3. Initiate Vapi calls for eligible contacts
    4. Handle retries for failed/unanswered calls

    Returns a summary of processed calls.
    """
    import main
    current_user = await main.get_current_user_flexible(request, db)

    # Verify admin or LO permissions
    _ensure_tables(db)

    from services.ai_outbound_scheduler import AIOutboundScheduler

    scheduler = AIOutboundScheduler(db)
    result = await scheduler.process_call_queue(max_calls=max_calls)

    return result


@router.delete("/queue/{call_id}")
async def cancel_queued_call(
    call_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """Cancel a pending call in the queue."""
    import main
    current_user = await main.get_current_user_flexible(request, db)

    _ensure_tables(db)

    try:
        result = db.execute(text("""
            UPDATE ai_outbound_calls
            SET status = 'cancelled', updated_at = :now
            WHERE call_id = :call_id AND lo_id = :lo_id AND status IN ('pending', 'retry_scheduled')
            RETURNING call_id
        """), {
            "call_id": call_id,
            "lo_id": current_user.id,
            "now": datetime.now(timezone.utc),
        }).fetchone()

        db.commit()

        if result:
            return {"success": True, "message": f"Call {call_id} cancelled"}
        else:
            raise HTTPException(
                status_code=404,
                detail="Call not found or cannot be cancelled (already in progress or completed)",
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelling call: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")
