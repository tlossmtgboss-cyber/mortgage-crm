"""
Cancellation Policy Routes

Endpoints for managing and enforcing appointment cancellation policies.

Endpoints:
  - GET    /cancellation-policy                   Get org policy (any authenticated user)
  - PUT    /cancellation-policy                   Update policy (admin only)
  - POST   /cancel/{appointment_id}               Cancel with policy enforcement
  - GET    /cancellation-policy/check/{appt_id}   Pre-flight policy check
  - GET    /cancellation-stats                     Cancellation analytics (admin only)
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from typing import List, Optional
import logging

from routes.scheduler._helpers import (
    get_current_user,
    _get_org_id,
    _is_scheduler_admin,
    _audit_log,
    _sanitize_text,
    _log_appointment_activity,
    _create_followup_task,
)
from db import get_db

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# REQUEST / RESPONSE MODELS
# ============================================================================

class CancellationPolicyUpdate(BaseModel):
    min_notice_hours: Optional[int] = Field(None, ge=0, le=720)
    max_cancellations_per_borrower: Optional[int] = Field(None, ge=0, le=100)
    allow_borrower_cancel: Optional[bool] = None
    require_reason: Optional[bool] = None
    cancellation_reasons: Optional[List[str]] = None
    late_cancel_message: Optional[str] = Field(None, max_length=2000)


class PolicyCancelRequest(BaseModel):
    reason: Optional[str] = Field(None, max_length=2000)
    notes: Optional[str] = Field(None, max_length=2000)
    cancelled_by_email: Optional[str] = Field(None, max_length=255)


# ============================================================================
# GET CANCELLATION POLICY
# ============================================================================

@router.get("/cancellation-policy")
async def get_cancellation_policy(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Get the cancellation policy for the current user's organization.

    Returns the full policy configuration including reasons list,
    notice period, and limits.
    """
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    from services.cancellation_policy_service import CancellationPolicyService
    svc = CancellationPolicyService(db)
    policy = svc.get_or_create_policy(org_id)
    db.commit()

    return {
        "id": policy.id,
        "organization_id": policy.organization_id,
        "min_notice_hours": policy.min_notice_hours,
        "max_cancellations_per_borrower": policy.max_cancellations_per_borrower,
        "allow_borrower_cancel": policy.allow_borrower_cancel,
        "require_reason": policy.require_reason,
        "cancellation_reasons": policy.cancellation_reasons or [],
        "late_cancel_message": policy.late_cancel_message or "",
        "created_at": policy.created_at.isoformat() if policy.created_at else None,
        "updated_at": policy.updated_at.isoformat() if policy.updated_at else None,
    }


# ============================================================================
# UPDATE CANCELLATION POLICY (ADMIN ONLY)
# ============================================================================

@router.put("/cancellation-policy")
async def update_cancellation_policy(
    body: CancellationPolicyUpdate,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Update the cancellation policy. Admin only.

    Only provided fields are updated -- omitted fields keep their current values.
    """
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    if not _is_scheduler_admin(user):
        raise HTTPException(status_code=403, detail="Admin access required")

    from services.cancellation_policy_service import CancellationPolicyService
    svc = CancellationPolicyService(db)

    # Build updates dict from non-None fields
    updates = {}
    if body.min_notice_hours is not None:
        updates["min_notice_hours"] = body.min_notice_hours
    if body.max_cancellations_per_borrower is not None:
        updates["max_cancellations_per_borrower"] = body.max_cancellations_per_borrower
    if body.allow_borrower_cancel is not None:
        updates["allow_borrower_cancel"] = body.allow_borrower_cancel
    if body.require_reason is not None:
        updates["require_reason"] = body.require_reason
    if body.cancellation_reasons is not None:
        updates["cancellation_reasons"] = body.cancellation_reasons
    if body.late_cancel_message is not None:
        updates["late_cancel_message"] = _sanitize_text(body.late_cancel_message)

    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    policy = svc.update_policy(org_id, updates)

    _audit_log(db, org_id, user.id, 'updated', 'cancellation_policy',
               entity_id=policy.id, changes=updates, request=request)

    db.commit()

    logger.info(f"Cancellation policy updated by user {user.id} (org {org_id}): {list(updates.keys())}")

    return {
        "id": policy.id,
        "organization_id": policy.organization_id,
        "min_notice_hours": policy.min_notice_hours,
        "max_cancellations_per_borrower": policy.max_cancellations_per_borrower,
        "allow_borrower_cancel": policy.allow_borrower_cancel,
        "require_reason": policy.require_reason,
        "cancellation_reasons": policy.cancellation_reasons or [],
        "late_cancel_message": policy.late_cancel_message or "",
        "updated_at": policy.updated_at.isoformat() if policy.updated_at else None,
    }


# ============================================================================
# PRE-FLIGHT POLICY CHECK
# ============================================================================

@router.get("/cancellation-policy/check/{appointment_id}")
async def check_cancellation_policy(
    appointment_id: int,
    cancelled_by_email: Optional[str] = Query(None, max_length=255),
    request: Request = None,
    db: Session = Depends(get_db),
):
    """
    Pre-flight check: can this appointment be cancelled?

    Returns policy check result without actually cancelling. Used by the
    frontend to show warnings before the user confirms.
    """
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    from services.cancellation_policy_service import CancellationPolicyService
    svc = CancellationPolicyService(db)

    check = svc.can_cancel(
        appointment_id=appointment_id,
        cancelled_by_email=cancelled_by_email,
        org_id=org_id,
        is_staff=True,  # Authenticated users are treated as staff
    )

    return check


# ============================================================================
# CANCEL WITH POLICY ENFORCEMENT
# ============================================================================

@router.post("/cancel/{appointment_id}")
async def cancel_with_policy(
    appointment_id: int,
    body: Optional[PolicyCancelRequest] = None,
    request: Request = None,
    db: Session = Depends(get_db),
):
    """
    Cancel an appointment with cancellation policy enforcement.

    This endpoint performs the full policy check before cancelling. If the
    policy denies the cancellation, the appointment remains unchanged and
    the response explains why.

    Staff users can always cancel but receive late-cancel warnings.
    """
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    reason = body.reason if body else None
    notes = body.notes if body else None
    cancelled_by_email = (body.cancelled_by_email if body else None) or getattr(user, 'email', None)

    # Sanitize inputs
    if reason:
        reason = _sanitize_text(reason)
    if notes:
        notes = _sanitize_text(notes)

    from services.cancellation_policy_service import CancellationPolicyService
    svc = CancellationPolicyService(db)

    result = svc.enforce_policy(
        appointment_id=appointment_id,
        cancelled_by_email=cancelled_by_email,
        org_id=org_id,
        reason=reason,
        notes=notes,
        is_staff=True,  # Authenticated users via this route are staff
        cancelled_by_user_id=user.id,
    )

    if not result["cancelled"]:
        # Policy denied -- return 409 with explanation
        raise HTTPException(
            status_code=409,
            detail={
                "message": result["policy_check"]["reason"],
                "policy_check": result["policy_check"],
            }
        )

    # Log CRM activity
    from routes.scheduler._helpers import get_models
    _models = get_models()
    Appointment = _models.get('Appointment') if _models else None
    appointment = None
    if Appointment:
        appointment = db.query(Appointment).filter(
            Appointment.id == appointment_id,
            Appointment.organization_id == org_id,
        ).first()

    if appointment:
        late_tag = " [LATE]" if result["is_late"] else ""
        _log_appointment_activity(
            db, org_id, user.id,
            getattr(appointment, 'lead_id', None),
            getattr(appointment, 'loan_id', None),
            f"Appointment cancelled{late_tag}: {appointment.title} - Reason: {reason or 'None given'}",
            activity_type="Note"
        )

        # Create re-engagement task
        from datetime import datetime as dt, timedelta as td, timezone as tz
        _create_followup_task(
            db, org_id,
            getattr(appointment, 'assigned_user_id', None) or user.id,
            getattr(appointment, 'lead_id', None),
            getattr(appointment, 'loan_id', None),
            title=f"Re-engage: {getattr(appointment, 'attendee_name', None) or 'cancelled booking'}"[:255],
            description=(
                f"Appointment '{appointment.title}' was cancelled. "
                f"Reason: {reason or 'None given'}. "
                f"{'Late cancellation. ' if result['is_late'] else ''}"
                f"Attempt to re-engage."
            ),
            due_date=dt.now(tz.utc) + td(days=1),
            priority="high"
        )

    _audit_log(db, org_id, user.id, 'policy_cancel', 'appointment',
               entity_id=appointment_id,
               changes={
                   'reason': reason,
                   'is_late': result["is_late"],
                   'cancel_count': result["policy_check"]["cancel_count"],
               },
               request=request)

    db.commit()

    logger.info(
        f"Policy-enforced cancel: appointment {appointment_id} by user {user.id} "
        f"(late={result['is_late']})"
    )

    return {
        "message": "Appointment cancelled",
        "appointment_id": appointment_id,
        "is_late": result["is_late"],
        "cancel_count": result["policy_check"]["cancel_count"],
        "policy_check": result["policy_check"],
    }


# ============================================================================
# CANCELLATION ANALYTICS (ADMIN ONLY)
# ============================================================================

@router.get("/cancellation-stats")
async def get_cancellation_stats(
    period_days: int = Query(30, ge=1, le=365),
    request: Request = None,
    db: Session = Depends(get_db),
):
    """
    Cancellation analytics for the admin dashboard.

    Returns cancellation rate, top reasons, repeat cancellers, and
    daily cancellation counts over the specified period.
    """
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    if not _is_scheduler_admin(user):
        raise HTTPException(status_code=403, detail="Admin access required")

    from services.cancellation_policy_service import CancellationPolicyService
    svc = CancellationPolicyService(db)

    stats = svc.get_cancellation_stats(org_id, period_days)

    return stats
