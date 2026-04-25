"""
Notification Action Routes

Quick-action endpoints called from iOS push notifications and the frontend
notification action handler (notificationActions.js).  These are thin wrappers
that either proxy to existing internal logic or provide the exact REST path the
clients expect.

Endpoints created here:
- PUT  /api/v1/tasks/{task_id}/complete             — Complete a task (iOS push action)
- POST /api/v1/loans/{loan_id}/rate-lock/extend
- POST /api/v1/smart-docs/delivery/send-reminder   (alias for /api/smart-docs/delivery/send-reminder)
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from db import get_db
from routes.auth_deps import current_user_dep, require_auth

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1",
    tags=["Notification Actions"],
    dependencies=[Depends(require_auth)],
)


# =============================================================================
# Pydantic models
# =============================================================================

class RateLockExtendResponse(BaseModel):
    success: bool
    loan_id: int
    extension_days: int
    new_expiration: str
    message: str


class DocReminderRequest(BaseModel):
    """Accepts both field-name patterns used by the frontend."""
    loan_id: int
    # notificationActions.js sends document_types; docDeliveryApi sends channels
    channels: List[str] = ["email"]
    document_types: Optional[List[str]] = None
    document_request_ids: Optional[List[int]] = None


class DocReminderResponse(BaseModel):
    success: bool
    loan_id: int
    channels_sent: List[str] = []
    channels_skipped: List[str] = []
    doc_count: int = 0
    portal_url: Optional[str] = None
    error: Optional[str] = None


# =============================================================================
# PUT /api/v1/tasks/{task_id}/complete
# =============================================================================


class TaskCompleteResponse(BaseModel):
    success: bool
    task_id: int
    status: str
    completed_at: Optional[str] = None
    message: str = "Task completed"


@router.put(
    "/tasks/{task_id}/complete",
    response_model=TaskCompleteResponse,
    summary="Complete a task — iOS push notification action",
)
async def complete_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(current_user_dep),
):
    """
    Mark a task as completed.

    Called from the iOS PushNotificationRouter ``completeTaskViaAPI()`` method
    when the user taps the "Complete Task" action button on a push notification.
    Also usable from any client that needs a simple PUT-to-complete semantic.

    Queries the ``tasks`` table (CRM tasks), scoped to the user's organisation.
    """
    from database.models.task import Task

    task = (
        db.query(Task)
        .filter(
            Task.id == task_id,
            Task.organization_id == current_user.organization_id,
        )
        .first()
    )
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.status == "completed":
        # Idempotent — already done
        return TaskCompleteResponse(
            success=True,
            task_id=task.id,
            status="completed",
            completed_at=task.completed_at.isoformat() if task.completed_at else None,
            message="Task was already completed",
        )

    now = datetime.now(timezone.utc)
    task.status = "completed"
    task.completed_at = now
    task.updated_at = now

    try:
        db.commit()
        db.refresh(task)
    except Exception as exc:
        db.rollback()
        logger.exception("Failed to complete task %s: %s", task_id, exc)
        raise HTTPException(status_code=500, detail="Failed to complete task")

    logger.info(
        "Task %s completed via push action by user %s",
        task_id, current_user.id,
    )

    return TaskCompleteResponse(
        success=True,
        task_id=task.id,
        status="completed",
        completed_at=task.completed_at.isoformat() if task.completed_at else None,
    )


# =============================================================================
# POST /api/v1/loans/{loan_id}/rate-lock/extend
# =============================================================================

@router.post(
    "/loans/{loan_id}/rate-lock/extend",
    response_model=RateLockExtendResponse,
    summary="Extend a rate lock — notification quick action",
)
async def extend_rate_lock(
    loan_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(current_user_dep),
):
    """
    Extend an active rate lock on a loan.

    Called from the iOS push notification "Extend Lock" quick action and from
    the frontend RATE_LOCK_EXPIRING notification category.  Delegates to
    the RateLockIntelligenceEngine for extension-day calculation.
    """
    # Lazy imports to avoid circular dependency
    from database.enums import RateLockStatus

    try:
        from database.models.lead_loan import Loan
    except ImportError:
        import main
        Loan = main.Loan

    # Query loan scoped to user's organisation
    org_id = getattr(current_user, "organization_id", None)
    loan = db.query(Loan).filter(
        Loan.id == loan_id,
        Loan.organization_id == org_id
    ).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    # Only extend if the lock is currently active or expiring
    current_status = getattr(loan, "rate_lock_status", None)
    if current_status not in (
        RateLockStatus.LOCKED,
        RateLockStatus.LOCK_EXPIRING,
        RateLockStatus.LOCK_EXTENDED,
    ):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot extend — current rate lock status is "
                   f"'{current_status.value if current_status else 'None'}'",
        )

    # Determine extension days via engine (falls back to 15 if engine unavailable)
    extension_days = 15
    try:
        from workflows.rate_lock_engine import RateLockIntelligenceEngine

        engine = RateLockIntelligenceEngine(loan, db)
        analysis = engine.analyze_extension_strategy()
        extension_days = analysis.get("recommended_extension_days", 15)
    except Exception as exc:
        logger.warning("RateLockIntelligenceEngine unavailable, defaulting to 15-day extension: %s", exc)

    # Apply extension
    now = datetime.now(timezone.utc)
    old_expiration = loan.lock_expiration_date

    loan.rate_lock_status = RateLockStatus.LOCK_EXTENDED
    loan.lock_expiration_date = (now + timedelta(days=extension_days))
    loan.lock_term_days = (loan.lock_term_days or 0) + extension_days

    # Append to history
    history = loan.rate_lock_history or []
    history.append({
        "action": "extend",
        "timestamp": now.isoformat(),
        "user_id": current_user.id,
        "extension_days": extension_days,
        "old_expiration": old_expiration.isoformat() if old_expiration else None,
        "new_expiration": loan.lock_expiration_date.isoformat() if loan.lock_expiration_date else None,
        "source": "notification_action",
    })
    loan.rate_lock_history = history

    try:
        db.commit()
        db.refresh(loan)
    except Exception as exc:
        db.rollback()
        logger.exception("Failed to extend rate lock for loan %s: %s", loan_id, exc)
        raise HTTPException(status_code=500, detail="Failed to extend rate lock")

    message = f"Lock extended by {extension_days} days. New expiration: {loan.lock_expiration_date}"
    logger.info("Rate lock extended for loan %s by user %s: %s", loan_id, current_user.id, message)

    return RateLockExtendResponse(
        success=True,
        loan_id=loan_id,
        extension_days=extension_days,
        new_expiration=loan.lock_expiration_date.isoformat() if loan.lock_expiration_date else None,
        message=message,
    )


# =============================================================================
# POST /api/v1/smart-docs/delivery/send-reminder
# =============================================================================

@router.post(
    "/smart-docs/delivery/send-reminder",
    response_model=DocReminderResponse,
    summary="Send document reminder — notification quick action",
)
async def send_doc_reminder(
    body: DocReminderRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user=Depends(current_user_dep),
):
    """
    Send a document reminder to the borrower for a specific loan.

    This endpoint lives at /api/v1/smart-docs/delivery/send-reminder to match
    the path the frontend notification action handler expects.  It delegates
    to the canonical delivery logic in smart_docs_delivery_routes.
    """
    try:
        from routes.smart_docs_delivery_routes import send_reminder as _canonical_send_reminder
        from routes.smart_docs_delivery_routes import SendReminderRequest

        # Map notification-action payload to the canonical request model
        canonical_body = SendReminderRequest(
            loan_id=body.loan_id,
            channels=body.channels,
            document_request_ids=body.document_request_ids,
        )
        return await _canonical_send_reminder(
            body=canonical_body,
            background_tasks=background_tasks,
            db=db,
            current_user=current_user,
        )
    except ImportError as exc:
        logger.warning("smart_docs_delivery_routes not available, falling back: %s", exc)
        # Minimal fallback — log the request so it is not silently lost
        logger.info(
            "Doc reminder requested for loan %s via notification action (delivery module unavailable)",
            body.loan_id,
        )
        return DocReminderResponse(
            success=False,
            loan_id=body.loan_id,
            error="Document delivery service is temporarily unavailable. Please try from the Smart Docs screen.",
        )
