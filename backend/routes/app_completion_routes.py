"""
Application Completion Orchestrator Routes

API endpoints for the AI-driven application completeness review system.
Provides endpoints for:
- Triggering and viewing application reviews
- Scoring page data aggregation
- Missing item management (resolve, escalate, defer, ask-borrower)
- Document staging and sending
- Communication logging and SMS webhooks
- PA appointment scheduling and completion
- Dashboard analytics and review queue

Auth: Every endpoint requires a valid JWT token via get_current_user.
Tenant isolation: All loan-based endpoints verify organization_id ownership.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import text as sa_text

from database import get_db
from auth.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/app-complete",
    tags=["Application Completion"],
)


# =============================================================================
# Pydantic Request / Response Models
# =============================================================================

class ReviewTriggerResponse(BaseModel):
    """Response from triggering a full application review."""
    review_id: int
    loan_id: str
    overall_score: float
    complexity_level: str
    next_action: str
    missing_items_count: int
    documents_staged: int
    text_resolvable: int
    call_needed: bool


class ResolveItemBody(BaseModel):
    """Body for staff resolving a missing item manually."""
    value: str = Field(..., description="The value to fill in")
    notes: Optional[str] = Field(None, description="Staff notes")


class StageDocumentBody(BaseModel):
    """Body for manually staging a document request."""
    doc_type: str
    doc_label: str
    reason: str = "manual_request"
    priority: str = "MEDIUM"


class SelectDocumentsBody(BaseModel):
    """Body for selecting documents for sending."""
    staging_ids: List[int]


class SendDocumentsBody(BaseModel):
    """Body for publishing selected docs to portal and notifying borrower."""
    staging_ids: Optional[List[int]] = None  # None = send all selected
    notify_sms: bool = True
    notify_email: bool = True


class WaiveDocumentBody(BaseModel):
    """Body for waiving a document requirement."""
    reason: str


class ScheduleAppointmentBody(BaseModel):
    """Body for scheduling a PA review call."""
    pa_user_id: Optional[str] = None
    start_time: str  # ISO datetime
    duration_minutes: int = 15


class CompleteCallBody(BaseModel):
    """Body for marking a call as completed."""
    items_resolved: List[int] = []
    call_notes: str = ""


class CancelAppointmentBody(BaseModel):
    """Body for cancelling a scheduled appointment."""
    reason: str = ""


class AskBorrowerBody(BaseModel):
    """Body for sending an SMS question to borrower."""
    custom_message: Optional[str] = None


# =============================================================================
# Helpers
# =============================================================================

def _verify_loan_tenant(db: Session, loan_id: int, current_user: Any) -> None:
    """Verify the requesting user's org owns the loan. Raises 404 if not."""
    org_id = getattr(current_user, "organization_id", None)
    is_platform_admin = getattr(current_user, "permission_role", "") == "admin"
    if org_id and not is_platform_admin:
        row = db.execute(
            sa_text("SELECT organization_id FROM loans WHERE id = :id"),
            {"id": loan_id},
        ).first()
        if row is None:
            raise HTTPException(status_code=404, detail="Loan not found")
        if row[0] is not None and row[0] != org_id:
            raise HTTPException(status_code=404, detail="Not found")


def _get_orchestrator(db: Session):
    """Get orchestrator service, raising 501 if unavailable."""
    try:
        from services.smart_docs.app_completion_orchestrator import (
            AppCompletionOrchestrator,
        )
        return AppCompletionOrchestrator(db)
    except ImportError:
        logger.warning("AppCompletionOrchestrator service not available")
        raise HTTPException(
            status_code=501,
            detail="Application completion service not available",
        )


def _get_user_id(current_user: Any) -> str:
    """Extract user ID as string."""
    uid = getattr(current_user, "id", None)
    return str(uid) if uid is not None else ""


def _get_org_id(current_user: Any) -> Optional[str]:
    """Extract organization ID as string."""
    org = getattr(current_user, "organization_id", None)
    return str(org) if org is not None else None


# =============================================================================
# 1. Trigger & Review Endpoints
# =============================================================================

@router.post("/review/{loan_id}")
async def trigger_application_review(
    loan_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Trigger a full application completeness review for a loan.

    Creates a new review record, scores all fields and documents,
    identifies gaps, stages missing documents, and builds an action plan.
    Returns the review summary with score, complexity, and next steps.
    """
    _verify_loan_tenant(db, loan_id, current_user)

    try:
        from services.smart_docs.app_completion_orchestrator import (
            trigger_application_review as _trigger_review,
        )
        orchestrator = _get_orchestrator(db)
        result = _trigger_review(
            db=db,
            loan_id=loan_id,
            triggered_by=_get_user_id(current_user),
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to trigger application review for loan {loan_id}")
        raise HTTPException(status_code=500, detail="Failed to trigger application review")


@router.get("/review/{loan_id}")
async def get_latest_review(
    loan_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Get the most recent application review for a loan.

    Returns full review details including score, missing items,
    staged documents, communication log, and appointment info.
    """
    _verify_loan_tenant(db, loan_id, current_user)

    try:
        orchestrator = _get_orchestrator(db)
        review = orchestrator.get_latest_review(loan_id)
        if not review:
            raise HTTPException(status_code=404, detail="No review found for this loan")
        return review
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get latest review for loan {loan_id}")
        raise HTTPException(status_code=500, detail="Failed to retrieve review")


@router.get("/review/{loan_id}/history")
async def get_review_history(
    loan_id: int,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Get all historical reviews for a loan, ordered by most recent first.

    Useful for tracking score improvement over time.
    """
    _verify_loan_tenant(db, loan_id, current_user)

    try:
        orchestrator = _get_orchestrator(db)
        history = orchestrator.get_review_history(
            loan_id=loan_id,
            limit=limit,
            offset=offset,
        )
        return history
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get review history for loan {loan_id}")
        raise HTTPException(status_code=500, detail="Failed to retrieve review history")


# =============================================================================
# 2. Scoring Page Endpoints
# =============================================================================

@router.get("/scoring/{loan_id}")
async def get_scoring_page(
    loan_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Get ALL data needed for the client scoring page in a single call.

    Returns: header info, missing items, clarifications needed, documents
    staged, exceptions, score history, recent communications, appointment
    coordination, and summary statistics.
    """
    _verify_loan_tenant(db, loan_id, current_user)

    try:
        orchestrator = _get_orchestrator(db)
        scoring_data = orchestrator.get_scoring_page_data(loan_id)
        if not scoring_data:
            raise HTTPException(
                status_code=404,
                detail="No review data found. Trigger a review first.",
            )
        return scoring_data
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get scoring page data for loan {loan_id}")
        raise HTTPException(status_code=500, detail="Failed to retrieve scoring data")


@router.get("/scoring/{loan_id}/trend")
async def get_score_trend(
    loan_id: int,
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Get score trend data for chart display.

    Returns timestamped score values over the requested period,
    suitable for rendering a line chart of completion progress.
    """
    _verify_loan_tenant(db, loan_id, current_user)

    try:
        orchestrator = _get_orchestrator(db)
        trend = orchestrator.get_score_trend(loan_id=loan_id, days=days)
        return trend
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get score trend for loan {loan_id}")
        raise HTTPException(status_code=500, detail="Failed to retrieve score trend")


# =============================================================================
# 3. Missing Items Endpoints
# =============================================================================

@router.get("/items/{loan_id}")
async def get_missing_items(
    loan_id: int,
    item_type: Optional[str] = Query(None, description="Filter by type: field, document, clarification"),
    severity: Optional[str] = Query(None, description="Filter by severity: CRITICAL, HIGH, MEDIUM, LOW"),
    status: Optional[str] = Query(None, description="Filter by status: open, resolved, deferred, escalated"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Get all missing items for a loan with optional filters.

    Returns categorized list of missing fields, documents, and
    clarifications needed, each with resolution method and priority.
    """
    _verify_loan_tenant(db, loan_id, current_user)

    try:
        orchestrator = _get_orchestrator(db)
        items = orchestrator.get_missing_items(
            loan_id=loan_id,
            item_type=item_type,
            severity=severity,
            status=status,
        )
        return items
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get missing items for loan {loan_id}")
        raise HTTPException(status_code=500, detail="Failed to retrieve missing items")


@router.post("/items/{item_id}/resolve")
async def resolve_item(
    item_id: int,
    body: ResolveItemBody,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Resolve a missing item by filling in the value manually.

    Staff provides the value and optional notes. The system updates
    the loan record, marks the item as resolved, and recalculates
    the overall completion score.
    """
    try:
        orchestrator = _get_orchestrator(db)

        # Verify tenant access through the item's loan
        item_info = orchestrator.get_item_loan_id(item_id)
        if not item_info:
            raise HTTPException(status_code=404, detail="Item not found")
        _verify_loan_tenant(db, item_info["loan_id"], current_user)

        result = orchestrator.resolve_item(
            item_id=item_id,
            value=body.value,
            notes=body.notes,
            resolved_by=_get_user_id(current_user),
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to resolve item {item_id}")
        raise HTTPException(status_code=500, detail="Failed to resolve item")


@router.post("/items/{item_id}/escalate")
async def escalate_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Escalate a missing item to a PA call.

    Marks the item for discussion during the next scheduled
    PA review call. If no call is scheduled, flags the loan
    as needing an appointment.
    """
    try:
        orchestrator = _get_orchestrator(db)

        item_info = orchestrator.get_item_loan_id(item_id)
        if not item_info:
            raise HTTPException(status_code=404, detail="Item not found")
        _verify_loan_tenant(db, item_info["loan_id"], current_user)

        result = orchestrator.escalate_item(
            item_id=item_id,
            escalated_by=_get_user_id(current_user),
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to escalate item {item_id}")
        raise HTTPException(status_code=500, detail="Failed to escalate item")


@router.post("/items/{item_id}/defer")
async def defer_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Defer a missing item, marking it as non-blocking.

    The item remains tracked but is excluded from the blocking
    score calculation. Useful for items that can be collected
    later in the process.
    """
    try:
        orchestrator = _get_orchestrator(db)

        item_info = orchestrator.get_item_loan_id(item_id)
        if not item_info:
            raise HTTPException(status_code=404, detail="Item not found")
        _verify_loan_tenant(db, item_info["loan_id"], current_user)

        result = orchestrator.defer_item(
            item_id=item_id,
            deferred_by=_get_user_id(current_user),
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to defer item {item_id}")
        raise HTTPException(status_code=500, detail="Failed to defer item")


@router.post("/items/{item_id}/ask-borrower")
async def ask_borrower(
    item_id: int,
    body: Optional[AskBorrowerBody] = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Send an SMS question to the borrower for a specific missing item.

    Uses the item's AI-generated question template or accepts a
    custom message override. The response is tracked and matched
    back to this item via the inbound SMS webhook.
    """
    try:
        orchestrator = _get_orchestrator(db)

        item_info = orchestrator.get_item_loan_id(item_id)
        if not item_info:
            raise HTTPException(status_code=404, detail="Item not found")
        _verify_loan_tenant(db, item_info["loan_id"], current_user)

        custom_message = body.custom_message if body else None
        result = orchestrator.ask_borrower(
            item_id=item_id,
            sent_by=_get_user_id(current_user),
            custom_message=custom_message,
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to send borrower question for item {item_id}")
        raise HTTPException(status_code=500, detail="Failed to send borrower question")


# =============================================================================
# 4. Document Staging Endpoints
# =============================================================================

@router.get("/documents/{loan_id}")
async def get_staged_documents(
    loan_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Get all staged document requests for a loan.

    Returns documents grouped by status: staged, selected, sent,
    received, waived. Each entry includes type, label, priority,
    reason, and current status.
    """
    _verify_loan_tenant(db, loan_id, current_user)

    try:
        orchestrator = _get_orchestrator(db)
        docs = orchestrator.get_staged_documents(loan_id)
        return docs
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get staged documents for loan {loan_id}")
        raise HTTPException(status_code=500, detail="Failed to retrieve staged documents")


@router.post("/documents/{loan_id}/stage")
async def stage_document(
    loan_id: int,
    body: StageDocumentBody,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Add a custom document request to the staging area.

    Staff can manually request additional documents beyond what
    the AI review identified. The document is staged for review
    before being sent to the borrower.
    """
    _verify_loan_tenant(db, loan_id, current_user)

    try:
        orchestrator = _get_orchestrator(db)
        result = orchestrator.stage_document(
            loan_id=loan_id,
            doc_type=body.doc_type,
            doc_label=body.doc_label,
            reason=body.reason,
            priority=body.priority,
            staged_by=_get_user_id(current_user),
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to stage document for loan {loan_id}")
        raise HTTPException(status_code=500, detail="Failed to stage document")


@router.post("/documents/select")
async def select_documents(
    body: SelectDocumentsBody,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Select specific staged documents for sending to the borrower.

    Marks the specified staging entries as selected. Use the
    send endpoint to publish them to the portal.
    """
    if not body.staging_ids:
        raise HTTPException(status_code=400, detail="No staging IDs provided")

    try:
        orchestrator = _get_orchestrator(db)

        # Verify tenant for each staging entry
        for staging_id in body.staging_ids:
            staging_info = orchestrator.get_staging_loan_id(staging_id)
            if not staging_info:
                raise HTTPException(
                    status_code=404,
                    detail=f"Staging entry {staging_id} not found",
                )
            _verify_loan_tenant(db, staging_info["loan_id"], current_user)

        result = orchestrator.select_documents(
            staging_ids=body.staging_ids,
            selected_by=_get_user_id(current_user),
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to select documents")
        raise HTTPException(status_code=500, detail="Failed to select documents")


@router.post("/documents/select-all/{loan_id}")
async def select_all_documents(
    loan_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Select all staged documents for a loan for sending.

    Convenience endpoint that marks every staged (unselected)
    document for the given loan as selected.
    """
    _verify_loan_tenant(db, loan_id, current_user)

    try:
        orchestrator = _get_orchestrator(db)
        result = orchestrator.select_all_documents(
            loan_id=loan_id,
            selected_by=_get_user_id(current_user),
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to select all documents for loan {loan_id}")
        raise HTTPException(status_code=500, detail="Failed to select all documents")


@router.post("/documents/send/{loan_id}")
async def send_documents(
    loan_id: int,
    body: SendDocumentsBody,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Publish selected documents to the borrower portal and notify.

    Creates portal tasks for each selected document, then sends
    SMS and/or email notifications to the borrower based on the
    request body flags.
    """
    _verify_loan_tenant(db, loan_id, current_user)

    try:
        orchestrator = _get_orchestrator(db)
        result = orchestrator.send_documents(
            loan_id=loan_id,
            staging_ids=body.staging_ids,
            notify_sms=body.notify_sms,
            notify_email=body.notify_email,
            sent_by=_get_user_id(current_user),
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to send documents for loan {loan_id}")
        raise HTTPException(status_code=500, detail="Failed to send documents")


@router.post("/documents/{staging_id}/waive")
async def waive_document(
    staging_id: int,
    body: WaiveDocumentBody,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Waive a document requirement with a reason.

    The document is removed from the borrower's task list and
    the completion score is recalculated. The waiver reason is
    logged for audit purposes.
    """
    try:
        orchestrator = _get_orchestrator(db)

        staging_info = orchestrator.get_staging_loan_id(staging_id)
        if not staging_info:
            raise HTTPException(status_code=404, detail="Staging entry not found")
        _verify_loan_tenant(db, staging_info["loan_id"], current_user)

        result = orchestrator.waive_document(
            staging_id=staging_id,
            reason=body.reason,
            waived_by=_get_user_id(current_user),
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to waive document {staging_id}")
        raise HTTPException(status_code=500, detail="Failed to waive document")


@router.get("/documents/{loan_id}/portal-tasks")
async def get_portal_tasks(
    loan_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Get borrower-facing task list for the portal API.

    Returns a simplified list of outstanding document requests
    formatted for the borrower portal UI. Each task includes
    a label, instructions, priority, and upload target.
    """
    _verify_loan_tenant(db, loan_id, current_user)

    try:
        orchestrator = _get_orchestrator(db)
        tasks = orchestrator.get_portal_tasks(loan_id)
        return tasks
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get portal tasks for loan {loan_id}")
        raise HTTPException(status_code=500, detail="Failed to retrieve portal tasks")


# =============================================================================
# 5. Communication Endpoints
# =============================================================================

@router.get("/comms/{loan_id}")
async def get_communication_log(
    loan_id: int,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Get communication log for a loan.

    Returns all SMS, email, and system messages related to the
    application completion process, ordered most recent first.
    """
    _verify_loan_tenant(db, loan_id, current_user)

    try:
        orchestrator = _get_orchestrator(db)
        comms = orchestrator.get_communication_log(
            loan_id=loan_id,
            limit=limit,
            offset=offset,
        )
        return comms
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get communication log for loan {loan_id}")
        raise HTTPException(status_code=500, detail="Failed to retrieve communication log")


@router.post("/comms/{loan_id}/send-intro")
async def send_intro_sequence(
    loan_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Start the intro SMS sequence manually for a loan.

    Sends the initial outreach message to the borrower introducing
    the document collection process. Normally triggered automatically
    by the review, but can be re-sent manually.
    """
    _verify_loan_tenant(db, loan_id, current_user)

    try:
        orchestrator = _get_orchestrator(db)
        result = orchestrator.send_intro_sequence(
            loan_id=loan_id,
            triggered_by=_get_user_id(current_user),
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to send intro sequence for loan {loan_id}")
        raise HTTPException(status_code=500, detail="Failed to send intro sequence")


@router.post("/comms/webhook/inbound-sms")
async def inbound_sms_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Webhook for incoming SMS from borrower (Telnyx payload).

    Receives the Telnyx webhook payload, extracts the sender phone
    and message body, matches to an active review, and routes to
    the orchestrator's handle_borrower_response method.

    This endpoint does NOT require user auth -- it is authenticated
    via Telnyx webhook signature verification.
    """
    try:
        payload = await request.json()
    except Exception as e:
        logger.exception("Failed to parse inbound SMS webhook payload")
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    try:
        # Extract Telnyx event data
        event_data = payload.get("data", {})
        event_payload = event_data.get("payload", {})

        from_number = event_payload.get("from", {}).get("phone_number", "")
        message_body = event_payload.get("text", "")
        to_number = event_payload.get("to", [{}])
        if isinstance(to_number, list) and to_number:
            to_number = to_number[0].get("phone_number", "")
        elif isinstance(to_number, dict):
            to_number = to_number.get("phone_number", "")

        if not from_number or not message_body:
            logger.warning("Inbound SMS webhook missing from_number or message body")
            return {"status": "ignored", "reason": "missing_fields"}

        orchestrator = _get_orchestrator(db)
        result = orchestrator.handle_borrower_response(
            from_number=from_number,
            to_number=to_number,
            message_body=message_body,
            raw_payload=payload,
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to process inbound SMS webhook")
        # Return 200 to Telnyx to avoid retries for processing errors
        return {"status": "error", "message": "Processing failed"}


# =============================================================================
# 6. Appointment Endpoints
# =============================================================================

@router.get("/appointment/{loan_id}")
async def get_appointment(
    loan_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Get current appointment coordination for a loan.

    Returns the scheduled or pending PA review call details,
    including assigned PA, time, duration, and items to discuss.
    """
    _verify_loan_tenant(db, loan_id, current_user)

    try:
        orchestrator = _get_orchestrator(db)
        appointment = orchestrator.get_appointment(loan_id)
        return appointment or {"loan_id": loan_id, "appointment": None, "status": "none"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get appointment for loan {loan_id}")
        raise HTTPException(status_code=500, detail="Failed to retrieve appointment")


@router.post("/appointment/{loan_id}/schedule")
async def schedule_appointment(
    loan_id: int,
    body: ScheduleAppointmentBody,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Schedule a PA review call for a loan.

    Creates an appointment record linking the loan to a PA user
    at the specified time. Sends calendar invite and notification.
    """
    _verify_loan_tenant(db, loan_id, current_user)

    try:
        orchestrator = _get_orchestrator(db)
        result = orchestrator.schedule_appointment(
            loan_id=loan_id,
            pa_user_id=body.pa_user_id or _get_user_id(current_user),
            start_time=body.start_time,
            duration_minutes=body.duration_minutes,
            scheduled_by=_get_user_id(current_user),
        )
        return result
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(f"Failed to schedule appointment for loan {loan_id}")
        raise HTTPException(status_code=500, detail="Failed to schedule appointment")


@router.post("/appointment/{appointment_id}/complete")
async def complete_appointment(
    appointment_id: int,
    body: CompleteCallBody,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Mark a PA review call as completed.

    Resolves the specified items discussed during the call,
    records call notes, and recalculates the completion score.
    """
    try:
        orchestrator = _get_orchestrator(db)

        appt_info = orchestrator.get_appointment_loan_id(appointment_id)
        if not appt_info:
            raise HTTPException(status_code=404, detail="Appointment not found")
        _verify_loan_tenant(db, appt_info["loan_id"], current_user)

        result = orchestrator.complete_appointment(
            appointment_id=appointment_id,
            items_resolved=body.items_resolved,
            call_notes=body.call_notes,
            completed_by=_get_user_id(current_user),
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to complete appointment {appointment_id}")
        raise HTTPException(status_code=500, detail="Failed to complete appointment")


@router.post("/appointment/{appointment_id}/cancel")
async def cancel_appointment(
    appointment_id: int,
    body: CancelAppointmentBody,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Cancel a scheduled PA review call.

    Marks the appointment as cancelled with the provided reason.
    Sends cancellation notification to the assigned PA.
    """
    try:
        orchestrator = _get_orchestrator(db)

        appt_info = orchestrator.get_appointment_loan_id(appointment_id)
        if not appt_info:
            raise HTTPException(status_code=404, detail="Appointment not found")
        _verify_loan_tenant(db, appt_info["loan_id"], current_user)

        result = orchestrator.cancel_appointment(
            appointment_id=appointment_id,
            reason=body.reason,
            cancelled_by=_get_user_id(current_user),
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to cancel appointment {appointment_id}")
        raise HTTPException(status_code=500, detail="Failed to cancel appointment")


# =============================================================================
# 7. Dashboard & Analytics Endpoints
# =============================================================================

@router.get("/dashboard")
async def get_dashboard(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Organization-wide application completion statistics.

    Returns aggregate metrics: average score, average time to
    complete, percentage resolved by AI, active review count,
    completion rate, and top missing item types.
    """
    org_id = _get_org_id(current_user)

    try:
        orchestrator = _get_orchestrator(db)
        dashboard = orchestrator.get_dashboard_stats(
            organization_id=org_id,
            days=days,
        )
        return dashboard
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to get dashboard statistics")
        raise HTTPException(status_code=500, detail="Failed to retrieve dashboard data")


@router.get("/queue")
async def get_review_queue(
    assigned_to: Optional[str] = Query(None, description="Filter by assigned user ID"),
    status: Optional[str] = Query(None, description="Filter by review status"),
    min_score: Optional[float] = Query(None, ge=0, le=100, description="Minimum completion score"),
    max_score: Optional[float] = Query(None, ge=0, le=100, description="Maximum completion score"),
    sort_by: str = Query("score_asc", description="Sort: score_asc, score_desc, created_desc, updated_desc"),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Get all active reviews for the organization.

    Returns paginated list with score, complexity level, next
    recommended action, borrower name, loan officer, and days
    since last activity. Supports filtering and sorting.
    """
    org_id = _get_org_id(current_user)

    try:
        orchestrator = _get_orchestrator(db)
        queue = orchestrator.get_review_queue(
            organization_id=org_id,
            assigned_to=assigned_to,
            status=status,
            min_score=min_score,
            max_score=max_score,
            sort_by=sort_by,
            limit=limit,
            offset=offset,
        )
        return queue
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to get review queue")
        raise HTTPException(status_code=500, detail="Failed to retrieve review queue")
