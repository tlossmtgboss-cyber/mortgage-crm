"""
Perennia Portal API Routes

FastAPI router for all portal-related endpoints including:
- Lifecycle management
- Milestone journey
- Close-On-Time calendar
- Home value intelligence
- Document management
- Notifications
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Path, Body
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import date, datetime
from decimal import Decimal
from pydantic import BaseModel, Field

from database import get_db
from models.portal_models import (
    LifecycleStage, MilestoneStatus, TaskStatus,
    DocumentType, DocumentStatus, NotificationChannel
)
from services.portal_lifecycle_service import PortalLifecycleService
from services.portal_milestone_service import PortalMilestoneService
from services.portal_close_on_time_service import PortalCloseOnTimeService
from services.portal_home_value_service import PortalHomeValueService
from services.portal_document_service import PortalDocumentService
from services.portal_notification_service import PortalNotificationService

router = APIRouter(prefix="/api/portal", tags=["Portal"])


# =============================================================================
# PYDANTIC MODELS
# =============================================================================

class StageTransitionRequest(BaseModel):
    new_stage: LifecycleStage
    reason: Optional[str] = None
    force: bool = False


class HeartbeatRequest(BaseModel):
    activity_type: str
    description: str
    metadata: Optional[dict] = None
    is_visible_to_borrower: bool = True


class RiskFlagRequest(BaseModel):
    risk_type: str
    severity: str = Field(..., pattern="^(low|medium|high|critical)$")
    description: str
    recommended_action: Optional[str] = None


class MilestoneUpdateRequest(BaseModel):
    status: MilestoneStatus
    notes: Optional[str] = None


class TaskUpdateRequest(BaseModel):
    status: TaskStatus
    metadata: Optional[dict] = None


class CloseScheduleRequest(BaseModel):
    target_close_date: date
    contract_date: Optional[date] = None


class PropertyBaselineRequest(BaseModel):
    baseline_value: Decimal
    baseline_date: date
    baseline_source: str
    property_state: str
    property_county: Optional[str] = None
    property_zip: Optional[str] = None
    property_msa: Optional[str] = None


class PropertyCostsRequest(BaseModel):
    monthly_property_tax: Optional[Decimal] = None
    monthly_hoi: Optional[Decimal] = None
    monthly_hoa: Optional[Decimal] = None
    monthly_pmi: Optional[Decimal] = None
    monthly_flood_insurance: Optional[Decimal] = None
    monthly_other: Optional[Decimal] = None


class DocumentStatusRequest(BaseModel):
    status: DocumentStatus
    rejection_reason: Optional[str] = None


class NotificationQueueRequest(BaseModel):
    event_type: str
    recipient_email: str
    recipient_phone: Optional[str] = None
    recipient_name: Optional[str] = None
    context: Optional[dict] = None
    channel: NotificationChannel = NotificationChannel.EMAIL
    scheduled_for: Optional[datetime] = None


# =============================================================================
# LIFECYCLE ENDPOINTS
# =============================================================================

@router.get("/loans/{loan_id}/status")
def get_portal_status(
    loan_id: int = Path(..., description="Loan ID"),
    db: Session = Depends(get_db),
):
    """Get comprehensive portal status for a loan."""
    service = PortalLifecycleService(db)
    return service.get_portal_status(loan_id)


@router.get("/loans/{loan_id}/lifecycle")
def get_lifecycle_stage(
    loan_id: int = Path(..., description="Loan ID"),
    db: Session = Depends(get_db),
):
    """Get current lifecycle stage with details."""
    service = PortalLifecycleService(db)
    return service.get_current_stage(loan_id)


@router.post("/loans/{loan_id}/lifecycle/transition")
def transition_lifecycle_stage(
    loan_id: int = Path(..., description="Loan ID"),
    request: StageTransitionRequest = Body(...),
    user_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Transition loan to a new lifecycle stage."""
    service = PortalLifecycleService(db)
    return service.transition_stage(
        loan_id=loan_id,
        new_stage=request.new_stage,
        transitioned_by=user_id,
        reason=request.reason,
        force=request.force,
    )


@router.get("/loans/{loan_id}/lifecycle/history")
def get_lifecycle_history(
    loan_id: int = Path(..., description="Loan ID"),
    db: Session = Depends(get_db),
):
    """Get lifecycle stage transition history."""
    service = PortalLifecycleService(db)
    return service.get_stage_history(loan_id)


@router.get("/loans/{loan_id}/lifecycle/valid-transitions")
def get_valid_transitions(
    loan_id: int = Path(..., description="Loan ID"),
    db: Session = Depends(get_db),
):
    """Get valid stage transitions from current stage."""
    service = PortalLifecycleService(db)
    return service.get_valid_transitions(loan_id)


# =============================================================================
# HEARTBEAT / ACTIVITY ENDPOINTS
# =============================================================================

@router.post("/loans/{loan_id}/heartbeat")
def record_heartbeat(
    loan_id: int = Path(..., description="Loan ID"),
    request: HeartbeatRequest = Body(...),
    user_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Record an activity for the loan heartbeat feature."""
    service = PortalLifecycleService(db)
    return service.record_heartbeat(
        loan_id=loan_id,
        activity_type=request.activity_type,
        description=request.description,
        metadata=request.metadata,
        actor=user_id,
        is_visible_to_borrower=request.is_visible_to_borrower,
    )


@router.get("/loans/{loan_id}/activity")
def get_recent_activity(
    loan_id: int = Path(..., description="Loan ID"),
    limit: int = Query(20, ge=1, le=100),
    borrower_visible_only: bool = Query(False),
    db: Session = Depends(get_db),
):
    """Get recent activity for loan heartbeat display."""
    service = PortalLifecycleService(db)
    return service.get_recent_activity(
        loan_id=loan_id,
        limit=limit,
        borrower_visible_only=borrower_visible_only,
    )


# =============================================================================
# RISK RADAR ENDPOINTS
# =============================================================================

@router.post("/loans/{loan_id}/risks")
def add_risk_flag(
    loan_id: int = Path(..., description="Loan ID"),
    request: RiskFlagRequest = Body(...),
    db: Session = Depends(get_db),
):
    """Add a risk flag to a loan."""
    service = PortalLifecycleService(db)
    return service.add_risk_flag(
        loan_id=loan_id,
        risk_type=request.risk_type,
        severity=request.severity,
        description=request.description,
        recommended_action=request.recommended_action,
    )


@router.get("/loans/{loan_id}/risks")
def get_active_risks(
    loan_id: int = Path(..., description="Loan ID"),
    db: Session = Depends(get_db),
):
    """Get active risk flags for a loan."""
    service = PortalLifecycleService(db)
    return service.get_active_risks(loan_id)


@router.post("/risks/{flag_id}/resolve")
def resolve_risk_flag(
    flag_id: int = Path(..., description="Risk flag ID"),
    resolution_notes: Optional[str] = Body(None),
    user_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Resolve a risk flag."""
    service = PortalLifecycleService(db)
    return service.resolve_risk_flag(
        flag_id=flag_id,
        resolved_by=user_id,
        resolution_notes=resolution_notes,
    )


# =============================================================================
# MILESTONE ENDPOINTS
# =============================================================================

@router.get("/loans/{loan_id}/milestones")
def get_loan_milestones(
    loan_id: int = Path(..., description="Loan ID"),
    include_tasks: bool = Query(True),
    borrower_view: bool = Query(False),
    db: Session = Depends(get_db),
):
    """Get all milestones for a loan with optional task details."""
    service = PortalMilestoneService(db)
    return service.get_loan_milestones(
        loan_id=loan_id,
        include_tasks=include_tasks,
        borrower_view=borrower_view,
    )


@router.get("/loans/{loan_id}/milestones/progress")
def get_milestone_progress(
    loan_id: int = Path(..., description="Loan ID"),
    db: Session = Depends(get_db),
):
    """Get overall milestone progress for a loan."""
    service = PortalMilestoneService(db)
    return service.get_milestone_progress(loan_id)


@router.post("/loans/{loan_id}/milestones/generate")
def generate_milestones(
    loan_id: int = Path(..., description="Loan ID"),
    stage: LifecycleStage = Query(...),
    expected_close_date: Optional[date] = Query(None),
    db: Session = Depends(get_db),
):
    """Generate milestone instances for a loan based on templates."""
    service = PortalMilestoneService(db)
    return service.generate_milestones_for_loan(
        loan_id=loan_id,
        stage=stage,
        expected_close_date=expected_close_date,
    )


@router.patch("/milestones/{milestone_id}")
def update_milestone(
    milestone_id: int = Path(..., description="Milestone ID"),
    request: MilestoneUpdateRequest = Body(...),
    user_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Update milestone status."""
    service = PortalMilestoneService(db)
    return service.update_milestone_status(
        milestone_id=milestone_id,
        status=request.status,
        notes=request.notes,
        updated_by=user_id,
    )


@router.get("/loans/{loan_id}/milestones/timeline")
def get_milestone_timeline(
    loan_id: int = Path(..., description="Loan ID"),
    view_type: str = Query("horizontal"),
    borrower_view: bool = Query(False),
    db: Session = Depends(get_db),
):
    """Get milestone data formatted for timeline visualization."""
    service = PortalMilestoneService(db)
    return service.get_timeline_data(
        loan_id=loan_id,
        view_type=view_type,
        borrower_view=borrower_view,
    )


@router.get("/loans/{loan_id}/milestones/summary")
def get_journey_summary(
    loan_id: int = Path(..., description="Loan ID"),
    db: Session = Depends(get_db),
):
    """Get journey summary for dashboard display."""
    service = PortalMilestoneService(db)
    return service.get_journey_summary(loan_id)


# =============================================================================
# TASK ENDPOINTS
# =============================================================================

@router.get("/tasks/{task_id}")
def get_task_details(
    task_id: int = Path(..., description="Task ID"),
    db: Session = Depends(get_db),
):
    """Get detailed task information."""
    service = PortalMilestoneService(db)
    result = service.get_task_details(task_id)
    if not result:
        raise HTTPException(status_code=404, detail="Task not found")
    return result


@router.patch("/tasks/{task_id}")
def update_task(
    task_id: int = Path(..., description="Task ID"),
    request: TaskUpdateRequest = Body(...),
    user_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Update task status."""
    service = PortalMilestoneService(db)
    return service.update_task_status(
        task_id=task_id,
        status=request.status,
        completed_by=user_id,
        metadata=request.metadata,
    )


@router.get("/loans/{loan_id}/tasks/borrower")
def get_borrower_tasks(
    loan_id: int = Path(..., description="Loan ID"),
    db: Session = Depends(get_db),
):
    """Get tasks requiring borrower action."""
    service = PortalMilestoneService(db)
    return service.get_pending_borrower_tasks(loan_id)


# =============================================================================
# CLOSE-ON-TIME CALENDAR ENDPOINTS
# =============================================================================

@router.post("/loans/{loan_id}/close-schedule")
def create_close_schedule(
    loan_id: int = Path(..., description="Loan ID"),
    request: CloseScheduleRequest = Body(...),
    db: Session = Depends(get_db),
):
    """Create a Close-On-Time schedule for a loan."""
    service = PortalCloseOnTimeService(db)
    return service.create_close_schedule(
        loan_id=loan_id,
        target_close_date=request.target_close_date,
        contract_date=request.contract_date,
    )


@router.get("/loans/{loan_id}/close-schedule")
def get_close_schedule(
    loan_id: int = Path(..., description="Loan ID"),
    db: Session = Depends(get_db),
):
    """Get Close-On-Time schedule for a loan."""
    service = PortalCloseOnTimeService(db)
    result = service.get_close_schedule(loan_id)
    if not result:
        raise HTTPException(status_code=404, detail="No close schedule found")
    return result


@router.get("/loans/{loan_id}/close-countdown")
def get_close_countdown(
    loan_id: int = Path(..., description="Loan ID"),
    db: Session = Depends(get_db),
):
    """Get countdown display data for a loan."""
    service = PortalCloseOnTimeService(db)
    return service.get_countdown_data(loan_id)


@router.get("/loans/{loan_id}/close-calendar")
def get_close_calendar(
    loan_id: int = Path(..., description="Loan ID"),
    start_date: Optional[date] = Query(None),
    weeks: int = Query(6, ge=1, le=12),
    db: Session = Depends(get_db),
):
    """Get calendar view data for Close-On-Time display."""
    service = PortalCloseOnTimeService(db)
    return service.get_calendar_view(
        loan_id=loan_id,
        start_date=start_date,
        weeks=weeks,
    )


@router.post("/close-milestones/{milestone_id}/complete")
def complete_close_milestone(
    milestone_id: int = Path(..., description="Close-On-Time milestone ID"),
    user_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Mark a Close-On-Time milestone as completed."""
    service = PortalCloseOnTimeService(db)
    return service.complete_schedule_milestone(
        milestone_id=milestone_id,
        completed_by=user_id,
    )


@router.get("/holidays/{year}")
def get_federal_holidays(
    year: int = Path(..., description="Year"),
    db: Session = Depends(get_db),
):
    """Get all federal holidays for a year."""
    service = PortalCloseOnTimeService(db)
    return service.get_holidays_for_year(year)


@router.post("/holidays/{year}/seed")
def seed_federal_holidays(
    year: int = Path(..., description="Year"),
    db: Session = Depends(get_db),
):
    """Seed federal holidays for a given year."""
    service = PortalCloseOnTimeService(db)
    return service.seed_federal_holidays(year)


@router.get("/business-days/count")
def count_business_days(
    start_date: date = Query(...),
    end_date: date = Query(...),
    db: Session = Depends(get_db),
):
    """Count business days between two dates."""
    service = PortalCloseOnTimeService(db)
    return {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "business_days": service.count_business_days(start_date, end_date),
    }


# =============================================================================
# HOME VALUE INTELLIGENCE ENDPOINTS
# =============================================================================

@router.post("/loans/{loan_id}/property-baseline")
def set_property_baseline(
    loan_id: int = Path(..., description="Loan ID"),
    request: PropertyBaselineRequest = Body(...),
    db: Session = Depends(get_db),
):
    """Set property value baseline."""
    service = PortalHomeValueService(db)
    return service.set_property_baseline(
        loan_id=loan_id,
        baseline_value=request.baseline_value,
        baseline_date=request.baseline_date,
        baseline_source=request.baseline_source,
        property_state=request.property_state,
        property_county=request.property_county,
        property_zip=request.property_zip,
        property_msa=request.property_msa,
    )


@router.get("/loans/{loan_id}/property-baseline")
def get_property_baseline(
    loan_id: int = Path(..., description="Loan ID"),
    db: Session = Depends(get_db),
):
    """Get property value baseline."""
    service = PortalHomeValueService(db)
    result = service.get_property_baseline(loan_id)
    if not result:
        raise HTTPException(status_code=404, detail="No property baseline found")
    return result


@router.get("/loans/{loan_id}/home-value")
def get_current_home_value(
    loan_id: int = Path(..., description="Loan ID"),
    db: Session = Depends(get_db),
):
    """Calculate current property value."""
    service = PortalHomeValueService(db)
    return service.calculate_current_value(loan_id)


@router.get("/loans/{loan_id}/home-value/dashboard")
def get_home_value_dashboard(
    loan_id: int = Path(..., description="Loan ID"),
    db: Session = Depends(get_db),
):
    """Get complete home value dashboard data."""
    service = PortalHomeValueService(db)
    return service.get_home_value_dashboard(loan_id)


@router.get("/loans/{loan_id}/equity")
def calculate_equity(
    loan_id: int = Path(..., description="Loan ID"),
    current_loan_balance: Decimal = Query(...),
    db: Session = Depends(get_db),
):
    """Calculate current equity position."""
    service = PortalHomeValueService(db)
    return service.calculate_equity(loan_id, current_loan_balance)


@router.get("/loans/{loan_id}/equity-unlock")
def calculate_equity_unlock(
    loan_id: int = Path(..., description="Loan ID"),
    current_loan_balance: Decimal = Query(...),
    max_ltv: Decimal = Query(Decimal("0.80")),
    db: Session = Depends(get_db),
):
    """Calculate potential equity available to unlock."""
    service = PortalHomeValueService(db)
    return service.calculate_equity_unlock(loan_id, current_loan_balance, max_ltv)


@router.get("/loans/{loan_id}/home-value/insights")
def get_home_value_insights(
    loan_id: int = Path(..., description="Loan ID"),
    db: Session = Depends(get_db),
):
    """Get active home value insights."""
    service = PortalHomeValueService(db)
    return service.get_active_insights(loan_id)


@router.post("/loans/{loan_id}/home-value/generate-insights")
def generate_home_value_insights(
    loan_id: int = Path(..., description="Loan ID"),
    db: Session = Depends(get_db),
):
    """Generate home value insights for a loan."""
    service = PortalHomeValueService(db)
    return service.generate_insights(loan_id)


@router.post("/insights/{insight_id}/dismiss")
def dismiss_insight(
    insight_id: int = Path(..., description="Insight ID"),
    db: Session = Depends(get_db),
):
    """Dismiss a home value insight."""
    service = PortalHomeValueService(db)
    return service.dismiss_insight(insight_id)


# =============================================================================
# DOCUMENT ENDPOINTS
# =============================================================================

@router.get("/loans/{loan_id}/documents")
def get_loan_documents(
    loan_id: int = Path(..., description="Loan ID"),
    document_type: Optional[DocumentType] = Query(None),
    status: Optional[DocumentStatus] = Query(None),
    borrower_view: bool = Query(False),
    db: Session = Depends(get_db),
):
    """Get all documents for a loan."""
    service = PortalDocumentService(db)
    return service.get_loan_documents(
        loan_id=loan_id,
        document_type=document_type,
        status=status,
        borrower_view=borrower_view,
    )


@router.get("/documents/{document_id}")
def get_document(
    document_id: int = Path(..., description="Document ID"),
    db: Session = Depends(get_db),
):
    """Get document details."""
    service = PortalDocumentService(db)
    result = service.get_document(document_id)
    if not result:
        raise HTTPException(status_code=404, detail="Document not found")
    return result


@router.patch("/documents/{document_id}/status")
def update_document_status(
    document_id: int = Path(..., description="Document ID"),
    request: DocumentStatusRequest = Body(...),
    user_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Update document status."""
    service = PortalDocumentService(db)
    return service.update_document_status(
        document_id=document_id,
        status=request.status,
        reviewed_by=user_id,
        rejection_reason=request.rejection_reason,
    )


@router.get("/documents/{document_id}/extraction")
def get_document_extraction(
    document_id: int = Path(..., description="Document ID"),
    db: Session = Depends(get_db),
):
    """Get extraction data for a document."""
    service = PortalDocumentService(db)
    result = service.get_extraction(document_id)
    if not result:
        raise HTTPException(status_code=404, detail="No extraction found")
    return result


@router.get("/loans/{loan_id}/documents/checklist")
def get_document_checklist(
    loan_id: int = Path(..., description="Loan ID"),
    lifecycle_stage: str = Query(...),
    db: Session = Depends(get_db),
):
    """Get document checklist for current lifecycle stage."""
    service = PortalDocumentService(db)
    return service.get_document_checklist(loan_id, lifecycle_stage)


@router.get("/loans/{loan_id}/documents/summary")
def get_document_summary(
    loan_id: int = Path(..., description="Loan ID"),
    db: Session = Depends(get_db),
):
    """Get document upload summary for a loan."""
    service = PortalDocumentService(db)
    return service.get_document_summary(loan_id)


@router.post("/loans/{loan_id}/property-costs")
def set_property_costs(
    loan_id: int = Path(..., description="Loan ID"),
    request: PropertyCostsRequest = Body(...),
    db: Session = Depends(get_db),
):
    """Set or update property costs for a loan."""
    service = PortalDocumentService(db)
    return service.set_property_costs(
        loan_id=loan_id,
        monthly_property_tax=request.monthly_property_tax,
        monthly_hoi=request.monthly_hoi,
        monthly_hoa=request.monthly_hoa,
        monthly_pmi=request.monthly_pmi,
        monthly_flood_insurance=request.monthly_flood_insurance,
        monthly_other=request.monthly_other,
    )


@router.get("/loans/{loan_id}/property-costs")
def get_property_costs(
    loan_id: int = Path(..., description="Loan ID"),
    db: Session = Depends(get_db),
):
    """Get property costs for a loan."""
    service = PortalDocumentService(db)
    result = service.get_property_costs(loan_id)
    if not result:
        raise HTTPException(status_code=404, detail="No property costs found")
    return result


# =============================================================================
# NOTIFICATION ENDPOINTS
# =============================================================================

@router.post("/loans/{loan_id}/notifications/queue")
def queue_notification(
    loan_id: int = Path(..., description="Loan ID"),
    request: NotificationQueueRequest = Body(...),
    db: Session = Depends(get_db),
):
    """Queue a notification for delivery."""
    service = PortalNotificationService(db)
    return service.queue_notification(
        loan_id=loan_id,
        event_type=request.event_type,
        recipient_email=request.recipient_email,
        recipient_phone=request.recipient_phone,
        recipient_name=request.recipient_name,
        context=request.context,
        channel=request.channel,
        scheduled_for=request.scheduled_for,
    )


@router.get("/loans/{loan_id}/notifications/history")
def get_notification_history(
    loan_id: int = Path(..., description="Loan ID"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """Get notification history for a loan."""
    service = PortalNotificationService(db)
    return service.get_notification_history(loan_id, limit)


@router.post("/notifications/process")
def process_notifications(
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """Process pending notifications in the queue."""
    service = PortalNotificationService(db)
    return service.process_pending_notifications(limit)


@router.get("/notifications/templates")
def get_notification_templates(
    event_type: Optional[str] = Query(None),
    channel: Optional[NotificationChannel] = Query(None),
    db: Session = Depends(get_db),
):
    """Get notification templates."""
    service = PortalNotificationService(db)
    return service.get_templates(event_type, channel)


# =============================================================================
# PARTNER PORTAL ENDPOINTS
# =============================================================================

@router.get("/partner/{access_token}")
def get_partner_portal_data(
    access_token: str = Path(..., description="Partner access token"),
    db: Session = Depends(get_db),
):
    """Get portal data for partner access (magic link)."""
    lifecycle_service = PortalLifecycleService(db)
    portal_loan = lifecycle_service.get_portal_loan_by_token(access_token)

    if not portal_loan:
        raise HTTPException(status_code=404, detail="Invalid or expired access token")

    if not portal_loan.partner_portal_enabled:
        raise HTTPException(status_code=403, detail="Partner portal not enabled")

    loan_id = portal_loan.loan_id

    # Get milestone data (partner-visible only)
    milestone_service = PortalMilestoneService(db)
    milestones = milestone_service.get_loan_milestones(
        loan_id=loan_id,
        include_tasks=False,
        borrower_view=False,  # Partner view
    )

    # Get close-on-time data
    close_service = PortalCloseOnTimeService(db)
    countdown = close_service.get_countdown_data(loan_id)

    return {
        "loan_id": loan_id,
        "lifecycle": lifecycle_service.get_current_stage(loan_id),
        "milestones": milestones,
        "countdown": countdown,
        "portal_type": "partner",
    }


# =============================================================================
# BORROWER PORTAL ENDPOINTS
# =============================================================================

@router.get("/borrower/{loan_id}/dashboard")
def get_borrower_dashboard(
    loan_id: int = Path(..., description="Loan ID"),
    db: Session = Depends(get_db),
):
    """Get comprehensive borrower dashboard data."""
    lifecycle_service = PortalLifecycleService(db)
    milestone_service = PortalMilestoneService(db)
    close_service = PortalCloseOnTimeService(db)
    document_service = PortalDocumentService(db)

    portal_loan = lifecycle_service.get_portal_loan(loan_id)

    if not portal_loan.portal_enabled:
        raise HTTPException(status_code=403, detail="Borrower portal not enabled")

    return {
        "loan_id": loan_id,
        "lifecycle": lifecycle_service.get_current_stage(loan_id),
        "milestone_progress": milestone_service.get_milestone_progress(loan_id),
        "journey_summary": milestone_service.get_journey_summary(loan_id),
        "countdown": close_service.get_countdown_data(loan_id),
        "documents": document_service.get_document_summary(loan_id),
        "recent_activity": lifecycle_service.get_recent_activity(
            loan_id, limit=5, borrower_visible_only=True
        ),
        "risks": lifecycle_service.get_active_risks(loan_id),
    }


@router.get("/borrower/{loan_id}/mum-dashboard")
def get_mum_dashboard(
    loan_id: int = Path(..., description="Loan ID"),
    db: Session = Depends(get_db),
):
    """Get MUM (Member Until Maturity) servicing dashboard."""
    lifecycle_service = PortalLifecycleService(db)
    home_value_service = PortalHomeValueService(db)

    portal_loan = lifecycle_service.get_portal_loan(loan_id)

    if portal_loan.lifecycle_stage not in [LifecycleStage.MUM, LifecycleStage.FUNDED]:
        raise HTTPException(
            status_code=400,
            detail="MUM dashboard only available for funded loans"
        )

    return {
        "loan_id": loan_id,
        "lifecycle": lifecycle_service.get_current_stage(loan_id),
        "home_value": home_value_service.get_home_value_dashboard(loan_id),
        "recent_activity": lifecycle_service.get_recent_activity(
            loan_id, limit=10, borrower_visible_only=True
        ),
    }
