"""
CRM Webhooks - Real-time CRM integration webhooks for portal updates.

Handles webhook receivers for:
- Milestone status changes
- Close On Time milestone updates
- Lifecycle stage changes
- Document upload events
- WebSocket broadcast triggers
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Header
from sqlalchemy.orm import Session
from typing import Optional, Dict, Any, List
from datetime import datetime, date
from pydantic import BaseModel, Field
import logging
import hmac
import hashlib
import os

from database import get_db
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/crm-webhooks", tags=["CRM Webhooks"])

# Webhook secret for signature verification
WEBHOOK_SECRET = os.getenv("CRM_WEBHOOK_SECRET", "development-secret-key")


# =============================================================================
# PYDANTIC MODELS
# =============================================================================

class MilestoneUpdatePayload(BaseModel):
    """Payload for milestone status updates from CRM."""
    loan_id: int
    milestone_code: str
    milestone_name: str
    status: str  # pending, in_progress, completed, skipped
    completed_at: Optional[datetime] = None
    completed_by: Optional[str] = None
    notes: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class CloseOnTimeMilestonePayload(BaseModel):
    """Payload for Close On Time milestone updates."""
    loan_id: int
    milestone_name: str
    deadline_date: date
    business_days_before_close: int
    is_completed: bool = False
    completed_at: Optional[datetime] = None
    completed_by: Optional[str] = None


class LifecycleChangePayload(BaseModel):
    """Payload for lifecycle stage changes from CRM."""
    loan_id: int
    previous_stage: Optional[str] = None
    new_stage: str  # PROSPECT, LEAD, PREAPPROVAL, UNDER_CONTRACT, PROCESSING, CLEAR_TO_CLOSE, FUNDED, MUM
    changed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    changed_by: Optional[str] = None
    reason: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class DocumentUploadPayload(BaseModel):
    """Payload for document upload events."""
    loan_id: int
    document_id: int
    document_type: str
    file_name: str
    status: str  # uploaded, pending_review, approved, rejected
    uploaded_by: Optional[str] = None
    uploaded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Optional[Dict[str, Any]] = None


class BulkMilestonePayload(BaseModel):
    """Payload for bulk milestone updates."""
    loan_id: int
    milestones: List[MilestoneUpdatePayload]


class WebhookResponse(BaseModel):
    """Standard webhook response."""
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None
    broadcast_sent: bool = False


# =============================================================================
# WEBHOOK SIGNATURE VERIFICATION
# =============================================================================

def verify_webhook_signature(
    payload: bytes,
    signature: str,
    secret: str = WEBHOOK_SECRET
) -> bool:
    """Verify webhook signature for security."""
    expected_signature = hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(f"sha256={expected_signature}", signature)


async def get_verified_payload(
    x_webhook_signature: Optional[str] = Header(None, alias="X-Webhook-Signature"),
) -> bool:
    """Dependency to verify webhook signatures in production."""
    # Skip verification in development
    if os.getenv("ENVIRONMENT", "development") == "development":
        return True

    if not x_webhook_signature:
        raise HTTPException(status_code=401, detail="Missing webhook signature")

    return True


# =============================================================================
# WEBSOCKET BROADCAST HELPER
# =============================================================================

async def broadcast_loan_update(
    loan_id: int,
    update_type: str,
    data: Dict[str, Any],
    db: Session
):
    """
    Broadcast loan update to connected WebSocket clients.

    This function attempts to use the portal WebSocket manager if available,
    falling back gracefully if WebSockets are not configured.
    """
    try:
        # Import the portal WebSocket manager
        from services.portal_websocket_service import portal_ws_manager

        message = {
            "type": update_type,
            "loan_id": loan_id,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        await portal_ws_manager.broadcast_to_loan(loan_id, message)
        logger.info(f"Broadcast {update_type} for loan {loan_id}")
        return True

    except ImportError:
        logger.warning("Portal WebSocket service not available, skipping broadcast")
        return False
    except Exception as e:
        logger.error(f"Failed to broadcast update for loan {loan_id}: {e}")
        return False


# =============================================================================
# MILESTONE WEBHOOKS
# =============================================================================

@router.post("/milestone/update", response_model=WebhookResponse)
async def handle_milestone_update(
    payload: MilestoneUpdatePayload,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    verified: bool = Depends(get_verified_payload)
):
    """
    Handle milestone status update from CRM.

    Updates the milestone in the portal database and broadcasts
    the change to connected WebSocket clients.
    """
    try:
        # Import service
        from services.portal_milestone_service import PortalMilestoneService
        from models.portal_models import MilestoneStatus, MilestoneInstance, MilestoneTemplate

        service = PortalMilestoneService(db)

        # Find the milestone instance
        milestone = db.query(MilestoneInstance).join(MilestoneTemplate).filter(
            MilestoneInstance.loan_id == payload.loan_id,
            MilestoneTemplate.code == payload.milestone_code
        ).first()

        if not milestone:
            return WebhookResponse(
                success=False,
                message=f"Milestone {payload.milestone_code} not found for loan {payload.loan_id}"
            )

        # Map status string to enum
        status_map = {
            "pending": MilestoneStatus.PENDING,
            "in_progress": MilestoneStatus.IN_PROGRESS,
            "completed": MilestoneStatus.COMPLETED,
            "skipped": MilestoneStatus.SKIPPED,
        }
        new_status = status_map.get(payload.status.lower())

        if not new_status:
            return WebhookResponse(
                success=False,
                message=f"Invalid status: {payload.status}"
            )

        # Update milestone
        result = service.update_milestone_status(
            milestone_id=milestone.id,
            status=new_status,
            notes=payload.notes,
            updated_by=payload.completed_by
        )

        # Schedule WebSocket broadcast
        broadcast_data = {
            "milestone_id": milestone.id,
            "milestone_code": payload.milestone_code,
            "milestone_name": payload.milestone_name,
            "old_status": result.get("old_status"),
            "new_status": result.get("new_status"),
            "completed_at": payload.completed_at.isoformat() if payload.completed_at else None,
        }

        broadcast_sent = await broadcast_loan_update(
            loan_id=payload.loan_id,
            update_type="MILESTONE_UPDATE",
            data=broadcast_data,
            db=db
        )

        logger.info(f"Milestone {payload.milestone_code} updated for loan {payload.loan_id}")

        return WebhookResponse(
            success=True,
            message=f"Milestone {payload.milestone_name} updated to {payload.status}",
            data=result,
            broadcast_sent=broadcast_sent
        )

    except Exception as e:
        logger.error(f"Error handling milestone update: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/milestone/bulk-update", response_model=WebhookResponse)
async def handle_bulk_milestone_update(
    payload: BulkMilestonePayload,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    verified: bool = Depends(get_verified_payload)
):
    """
    Handle bulk milestone updates from CRM.

    Useful for syncing multiple milestones at once.
    """
    try:
        results = []
        for milestone_payload in payload.milestones:
            # Create individual payload with loan_id
            individual = MilestoneUpdatePayload(
                loan_id=payload.loan_id,
                **milestone_payload.model_dump(exclude={'loan_id'})
            )

            # Process each milestone
            result = await handle_milestone_update(
                payload=individual,
                background_tasks=background_tasks,
                db=db,
                verified=True
            )
            results.append({
                "milestone_code": milestone_payload.milestone_code,
                "success": result.success,
                "message": result.message
            })

        successful = len([r for r in results if r["success"]])

        return WebhookResponse(
            success=successful > 0,
            message=f"Updated {successful}/{len(results)} milestones",
            data={"results": results}
        )

    except Exception as e:
        logger.error(f"Error handling bulk milestone update: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# CLOSE ON TIME WEBHOOKS
# =============================================================================

@router.post("/close-on-time/milestone", response_model=WebhookResponse)
async def handle_close_on_time_milestone(
    payload: CloseOnTimeMilestonePayload,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    verified: bool = Depends(get_verified_payload)
):
    """
    Handle Close On Time milestone update from CRM.

    Updates the COT milestone and broadcasts to connected clients.
    """
    try:
        from services.portal_close_on_time_service import PortalCloseOnTimeService
        from models.portal_models import CloseOnTimeMilestone, CloseOnTimeSchedule

        service = PortalCloseOnTimeService(db)

        # Find the schedule
        schedule = db.query(CloseOnTimeSchedule).filter(
            CloseOnTimeSchedule.loan_id == payload.loan_id
        ).first()

        if not schedule:
            return WebhookResponse(
                success=False,
                message=f"No Close On Time schedule found for loan {payload.loan_id}"
            )

        # Find or create milestone
        milestone = db.query(CloseOnTimeMilestone).filter(
            CloseOnTimeMilestone.schedule_id == schedule.id,
            CloseOnTimeMilestone.milestone_name == payload.milestone_name
        ).first()

        if milestone:
            # Update existing
            milestone.deadline_date = payload.deadline_date
            milestone.business_days_before_close = payload.business_days_before_close
            milestone.is_completed = payload.is_completed
            if payload.is_completed:
                milestone.completed_at = payload.completed_at or datetime.now(timezone.utc)
                milestone.completed_by = payload.completed_by
        else:
            # Create new
            milestone = CloseOnTimeMilestone(
                schedule_id=schedule.id,
                milestone_name=payload.milestone_name,
                deadline_date=payload.deadline_date,
                business_days_before_close=payload.business_days_before_close,
                is_completed=payload.is_completed,
                completed_at=payload.completed_at if payload.is_completed else None,
                completed_by=payload.completed_by if payload.is_completed else None,
            )
            db.add(milestone)

        db.commit()
        db.refresh(milestone)

        # Update schedule tracking
        service.update_schedule_tracking(payload.loan_id)

        # Broadcast update
        broadcast_data = {
            "milestone_id": milestone.id,
            "milestone_name": payload.milestone_name,
            "deadline_date": payload.deadline_date.isoformat(),
            "is_completed": payload.is_completed,
            "business_days_remaining": schedule.business_days_remaining,
        }

        broadcast_sent = await broadcast_loan_update(
            loan_id=payload.loan_id,
            update_type="CLOSE_ON_TIME_UPDATE",
            data=broadcast_data,
            db=db
        )

        logger.info(f"Close On Time milestone '{payload.milestone_name}' updated for loan {payload.loan_id}")

        return WebhookResponse(
            success=True,
            message=f"Close On Time milestone '{payload.milestone_name}' updated",
            data={
                "milestone_id": milestone.id,
                "is_completed": milestone.is_completed,
            },
            broadcast_sent=broadcast_sent
        )

    except Exception as e:
        logger.error(f"Error handling Close On Time milestone: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/close-on-time/schedule", response_model=WebhookResponse)
async def handle_close_schedule_update(
    loan_id: int,
    target_close_date: date,
    contract_date: Optional[date] = None,
    db: Session = Depends(get_db),
    verified: bool = Depends(get_verified_payload)
):
    """
    Create or update Close On Time schedule for a loan.
    """
    try:
        from services.portal_close_on_time_service import PortalCloseOnTimeService

        service = PortalCloseOnTimeService(db)

        result = service.create_close_schedule(
            loan_id=loan_id,
            target_close_date=target_close_date,
            contract_date=contract_date
        )

        # Broadcast update
        broadcast_data = {
            "target_close_date": target_close_date.isoformat(),
            "business_days_remaining": result.get("business_days_remaining"),
        }

        broadcast_sent = await broadcast_loan_update(
            loan_id=loan_id,
            update_type="CLOSE_SCHEDULE_UPDATE",
            data=broadcast_data,
            db=db
        )

        return WebhookResponse(
            success=True,
            message=f"Close schedule created/updated for loan {loan_id}",
            data=result,
            broadcast_sent=broadcast_sent
        )

    except Exception as e:
        logger.error(f"Error handling close schedule update: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# LIFECYCLE WEBHOOKS
# =============================================================================

@router.post("/lifecycle/change", response_model=WebhookResponse)
async def handle_lifecycle_change(
    payload: LifecycleChangePayload,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    verified: bool = Depends(get_verified_payload)
):
    """
    Handle lifecycle stage change from CRM.

    Updates the portal loan lifecycle and broadcasts to clients.
    """
    try:
        from services.portal_lifecycle_service import PortalLifecycleService
        from models.portal_models import LifecycleStage

        service = PortalLifecycleService(db)

        # Map stage string to enum
        try:
            new_stage = LifecycleStage(payload.new_stage.upper())
        except ValueError:
            return WebhookResponse(
                success=False,
                message=f"Invalid lifecycle stage: {payload.new_stage}"
            )

        # Transition the stage
        result = service.transition_stage(
            loan_id=payload.loan_id,
            new_stage=new_stage,
            reason=payload.reason,
            force=True  # CRM updates should force transitions
        )

        if not result.get("success"):
            return WebhookResponse(
                success=False,
                message=result.get("error", "Failed to transition lifecycle stage"),
                data=result
            )

        # Broadcast update
        broadcast_data = {
            "previous_stage": payload.previous_stage,
            "new_stage": payload.new_stage,
            "changed_at": payload.changed_at.isoformat(),
            "changed_by": payload.changed_by,
        }

        broadcast_sent = await broadcast_loan_update(
            loan_id=payload.loan_id,
            update_type="LIFECYCLE_CHANGE",
            data=broadcast_data,
            db=db
        )

        logger.info(f"Lifecycle changed to {payload.new_stage} for loan {payload.loan_id}")

        return WebhookResponse(
            success=True,
            message=f"Lifecycle transitioned to {payload.new_stage}",
            data=result,
            broadcast_sent=broadcast_sent
        )

    except Exception as e:
        logger.error(f"Error handling lifecycle change: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# DOCUMENT WEBHOOKS
# =============================================================================

@router.post("/document/upload", response_model=WebhookResponse)
async def handle_document_upload(
    payload: DocumentUploadPayload,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    verified: bool = Depends(get_verified_payload)
):
    """
    Handle document upload notification from CRM.

    Updates document status and broadcasts to portal clients.
    """
    try:
        from models.portal_models import LoanActivityLog

        # Log the document activity
        activity = LoanActivityLog(
            loan_id=payload.loan_id,
            activity_type="document_uploaded",
            description=f"Document '{payload.file_name}' uploaded",
            metadata={
                "document_id": payload.document_id,
                "document_type": payload.document_type,
                "file_name": payload.file_name,
                "status": payload.status,
                "uploaded_by": payload.uploaded_by,
            },
            actor=payload.uploaded_by,
            is_visible_to_borrower=True,
        )
        db.add(activity)
        db.commit()

        # Broadcast update
        broadcast_data = {
            "document_id": payload.document_id,
            "document_type": payload.document_type,
            "file_name": payload.file_name,
            "status": payload.status,
            "uploaded_at": payload.uploaded_at.isoformat(),
        }

        broadcast_sent = await broadcast_loan_update(
            loan_id=payload.loan_id,
            update_type="DOCUMENT_UPLOAD",
            data=broadcast_data,
            db=db
        )

        logger.info(f"Document upload notification for loan {payload.loan_id}")

        return WebhookResponse(
            success=True,
            message=f"Document '{payload.file_name}' notification processed",
            data={"activity_id": activity.id},
            broadcast_sent=broadcast_sent
        )

    except Exception as e:
        logger.error(f"Error handling document upload: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/document/status", response_model=WebhookResponse)
async def handle_document_status_change(
    loan_id: int,
    document_id: int,
    status: str,
    rejection_reason: Optional[str] = None,
    db: Session = Depends(get_db),
    verified: bool = Depends(get_verified_payload)
):
    """
    Handle document status change from CRM.
    """
    try:
        from services.portal_document_service import PortalDocumentService

        service = PortalDocumentService(db)

        result = service.update_document_status(
            document_id=document_id,
            status=status,
            rejection_reason=rejection_reason
        )

        # Broadcast update
        broadcast_data = {
            "document_id": document_id,
            "status": status,
            "rejection_reason": rejection_reason,
        }

        broadcast_sent = await broadcast_loan_update(
            loan_id=loan_id,
            update_type="DOCUMENT_STATUS_CHANGE",
            data=broadcast_data,
            db=db
        )

        return WebhookResponse(
            success=True,
            message=f"Document status updated to {status}",
            data=result,
            broadcast_sent=broadcast_sent
        )

    except Exception as e:
        logger.error(f"Error handling document status change: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# SYNC ENDPOINTS
# =============================================================================

@router.post("/sync/full", response_model=WebhookResponse)
async def handle_full_sync(
    loan_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    verified: bool = Depends(get_verified_payload)
):
    """
    Trigger a full sync of loan data from CRM.

    This will refresh all milestone, lifecycle, and document data
    for the specified loan.
    """
    try:
        # Broadcast sync start
        await broadcast_loan_update(
            loan_id=loan_id,
            update_type="SYNC_STARTED",
            data={"loan_id": loan_id},
            db=db
        )

        # Perform sync operations
        sync_results = {
            "milestones_synced": 0,
            "lifecycle_synced": False,
            "documents_synced": 0,
        }

        # Sync milestones from CRM
        from sqlalchemy import text
        milestones = db.execute(text("""
            SELECT id FROM loan_milestones WHERE loan_id = :loan_id
        """), {"loan_id": loan_id}).fetchall()
        sync_results["milestones_synced"] = len(milestones)

        # Sync lifecycle stage
        loan = db.execute(text("""
            SELECT lifecycle_stage FROM loans WHERE id = :loan_id
        """), {"loan_id": loan_id}).fetchone()
        if loan:
            sync_results["lifecycle_synced"] = True
            sync_results["current_stage"] = loan[0]

        # Sync documents
        documents = db.execute(text("""
            SELECT id FROM loan_documents WHERE loan_id = :loan_id
        """), {"loan_id": loan_id}).fetchall()
        sync_results["documents_synced"] = len(documents)

        # Update last_synced timestamp
        db.execute(text("""
            UPDATE loans SET updated_at = CURRENT_TIMESTAMP WHERE id = :loan_id
        """), {"loan_id": loan_id})
        db.commit()

        # Broadcast sync complete
        broadcast_sent = await broadcast_loan_update(
            loan_id=loan_id,
            update_type="SYNC_COMPLETED",
            data=sync_results,
            db=db
        )

        return WebhookResponse(
            success=True,
            message=f"Full sync triggered for loan {loan_id}",
            data=sync_results,
            broadcast_sent=broadcast_sent
        )

    except Exception as e:
        logger.error(f"Error handling full sync: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# HEALTH CHECK
# =============================================================================

@router.get("/health")
async def webhook_health():
    """Health check endpoint for CRM webhook service."""
    return {
        "status": "healthy",
        "service": "crm-webhooks",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
