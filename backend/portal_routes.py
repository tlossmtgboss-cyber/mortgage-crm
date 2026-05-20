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

from fastapi import APIRouter, Depends, HTTPException, Query, Path, Body, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import date, datetime
from decimal import Decimal
from pydantic import BaseModel, Field
import logging

logger = logging.getLogger(__name__)

from database import get_db
from middleware.purl_auth import require_purl_token, require_purl_write_scope, PURLAuthContext
from utils.auth import require_admin

# Lazy import to avoid circular dependencies
def get_current_user_dep():
    """Get current user dependency - lazy import to avoid circular imports"""
    from auth.dependencies import get_current_user
    return get_current_user

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

router = APIRouter(prefix="/api/v1/portal", tags=["Portal"])


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
    current_user=Depends(get_current_user_dep()),
):
    """Get comprehensive portal status for a loan."""
    service = PortalLifecycleService(db)
    return service.get_portal_status(loan_id)


@router.get("/loans/{loan_id}/lifecycle")
def get_lifecycle_stage(
    loan_id: int = Path(..., description="Loan ID"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    """Get current lifecycle stage with details."""
    service = PortalLifecycleService(db)
    return service.get_current_stage(loan_id)


@router.post("/loans/{loan_id}/lifecycle/transition")
def transition_lifecycle_stage(
    loan_id: int = Path(..., description="Loan ID"),
    request: StageTransitionRequest = Body(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    """Transition loan to a new lifecycle stage."""
    service = PortalLifecycleService(db)
    return service.transition_stage(
        loan_id=loan_id,
        new_stage=request.new_stage,
        transitioned_by=str(current_user.id),
        reason=request.reason,
        force=request.force,
    )


@router.get("/loans/{loan_id}/lifecycle/history")
def get_lifecycle_history(
    loan_id: int = Path(..., description="Loan ID"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    """Get lifecycle stage transition history."""
    service = PortalLifecycleService(db)
    return service.get_stage_history(loan_id)


@router.get("/loans/{loan_id}/lifecycle/valid-transitions")
def get_valid_transitions(
    loan_id: int = Path(..., description="Loan ID"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
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
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    """Record an activity for the loan heartbeat feature."""
    service = PortalLifecycleService(db)
    return service.record_heartbeat(
        loan_id=loan_id,
        activity_type=request.activity_type,
        description=request.description,
        metadata=request.metadata,
        actor=str(current_user.id),
        is_visible_to_borrower=request.is_visible_to_borrower,
    )


@router.get("/loans/{loan_id}/activity")
def get_recent_activity(
    loan_id: int = Path(..., description="Loan ID"),
    limit: int = Query(20, ge=1, le=100),
    borrower_visible_only: bool = Query(False),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    """Get recent activity for loan heartbeat display."""
    try:
        service = PortalLifecycleService(db)
        result = service.get_recent_activity(
            loan_id=loan_id,
            limit=limit,
            borrower_visible_only=borrower_visible_only,
        )
        return result
    except Exception as e:
        import traceback
        logger.error(f"Activity endpoint error: {e}")
        logger.error(traceback.format_exc())
        raise


# =============================================================================
# RISK RADAR ENDPOINTS
# =============================================================================

@router.post("/loans/{loan_id}/risks")
def add_risk_flag(
    loan_id: int = Path(..., description="Loan ID"),
    request: RiskFlagRequest = Body(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
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
    current_user=Depends(get_current_user_dep()),
):
    """Get active risk flags for a loan."""
    service = PortalLifecycleService(db)
    return service.get_active_risks(loan_id)


@router.post("/risks/{flag_id}/resolve")
def resolve_risk_flag(
    flag_id: int = Path(..., description="Risk flag ID"),
    resolution_notes: Optional[str] = Body(None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    """Resolve a risk flag."""
    service = PortalLifecycleService(db)
    return service.resolve_risk_flag(
        flag_id=flag_id,
        resolved_by=str(current_user.id),
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
    current_user=Depends(get_current_user_dep()),
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
    current_user=Depends(get_current_user_dep()),
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
    current_user=Depends(get_current_user_dep()),
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
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    """Update milestone status."""
    service = PortalMilestoneService(db)
    return service.update_milestone_status(
        milestone_id=milestone_id,
        status=request.status,
        notes=request.notes,
        updated_by=str(current_user.id),
    )


@router.get("/loans/{loan_id}/milestones/timeline")
def get_milestone_timeline(
    loan_id: int = Path(..., description="Loan ID"),
    view_type: str = Query("horizontal"),
    borrower_view: bool = Query(False),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
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
    current_user=Depends(get_current_user_dep()),
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
    current_user=Depends(get_current_user_dep()),
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
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    """Update task status."""
    service = PortalMilestoneService(db)
    return service.update_task_status(
        task_id=task_id,
        status=request.status,
        completed_by=str(current_user.id),
        metadata=request.metadata,
    )


@router.get("/loans/{loan_id}/tasks/borrower")
def get_borrower_tasks(
    loan_id: int = Path(..., description="Loan ID"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
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
    current_user=Depends(get_current_user_dep()),
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
    current_user=Depends(get_current_user_dep()),
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
    current_user=Depends(get_current_user_dep()),
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
    current_user=Depends(get_current_user_dep()),
):
    """Get calendar view data for Close-On-Time display."""
    service = PortalCloseOnTimeService(db)
    return service.get_calendar_view(
        loan_id=loan_id,
        start_date=start_date,
        weeks=weeks,
    )


@router.get("/loans/{loan_id}/milestone-calendar.ics")
def generate_milestone_calendar(
    loan_id: int = Path(..., description="Loan ID"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    """
    Generate and download an ICS calendar file with all loan milestones.

    This creates a downloadable calendar file that can be imported into
    Google Calendar, Apple Calendar, Outlook, etc.
    """
    from utils.calendar_invite import generate_milestone_calendar_ics
    from models.portal_models import PortalLoan, CloseOnTimeSchedule, CloseOnTimeMilestone

    # Get loan details
    loan = db.query(PortalLoan).filter(PortalLoan.id == loan_id).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    # Get borrower name
    borrower_name = "Borrower"
    if loan.borrower_id:
        from models import Contact
        contact = db.query(Contact).filter(Contact.id == loan.borrower_id).first()
        if contact:
            borrower_name = f"{contact.first_name or ''} {contact.last_name or ''}".strip() or "Borrower"

    # Get loan officer name if available
    loan_officer_name = None
    if loan.assigned_lo_id:
        from models import User
        lo = db.query(User).filter(User.id == loan.assigned_lo_id).first()
        if lo:
            loan_officer_name = lo.full_name

    # Get close-on-time schedule and milestones
    schedule = db.query(CloseOnTimeSchedule).filter(
        CloseOnTimeSchedule.loan_id == loan_id
    ).first()

    milestones = []
    target_close_date = None

    if schedule:
        target_close_date = schedule.target_close_date

        # Get all milestones for this schedule
        schedule_milestones = db.query(CloseOnTimeMilestone).filter(
            CloseOnTimeMilestone.schedule_id == schedule.id
        ).order_by(CloseOnTimeMilestone.due_date).all()

        for m in schedule_milestones:
            milestones.append({
                "name": m.milestone_name,
                "description": m.milestone_description or "",
                "due_date": m.due_date,
                "status": m.status or "pending",
            })

    # Also get milestones from the MilestoneInstance table (lifecycle milestones)
    from models.portal_models import MilestoneInstance
    lifecycle_milestones = db.query(MilestoneInstance).filter(
        MilestoneInstance.loan_id == loan_id
    ).all()

    for m in lifecycle_milestones:
        if m.target_date:
            status = "pending"
            if m.status:
                status = m.status.value if hasattr(m.status, 'value') else str(m.status)
            milestones.append({
                "name": m.name,
                "description": m.description or "",
                "due_date": m.target_date,
                "status": status,
            })

    if not milestones and not target_close_date:
        raise HTTPException(
            status_code=404,
            detail="No milestones found for this loan. Please set up a closing schedule first."
        )

    # Generate ICS content
    ics_content = generate_milestone_calendar_ics(
        loan_number=loan.loan_number or str(loan_id),
        borrower_name=borrower_name,
        property_address=loan.property_address,
        milestones=milestones,
        target_close_date=target_close_date,
        loan_officer_name=loan_officer_name,
    )

    # Return as downloadable ICS file
    filename = f"loan-{loan.loan_number or loan_id}-milestones.ics"

    return Response(
        content=ics_content,
        media_type="text/calendar",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": "text/calendar; charset=utf-8",
        }
    )


@router.post("/close-milestones/{milestone_id}/complete")
def complete_close_milestone(
    milestone_id: int = Path(..., description="Close-On-Time milestone ID"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    """Mark a Close-On-Time milestone as completed."""
    service = PortalCloseOnTimeService(db)
    return service.complete_schedule_milestone(
        milestone_id=milestone_id,
        completed_by=str(current_user.id),
    )


@router.get("/holidays/{year}")
def get_federal_holidays(
    year: int = Path(..., description="Year"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    """Get all federal holidays for a year."""
    service = PortalCloseOnTimeService(db)
    return service.get_holidays_for_year(year)


@router.post("/holidays/{year}/seed")
def seed_federal_holidays(
    year: int = Path(..., description="Year"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    """Seed federal holidays for a given year. Requires admin access."""
    require_admin(current_user)
    service = PortalCloseOnTimeService(db)
    return service.seed_federal_holidays(year)


@router.get("/business-days/count")
def count_business_days(
    start_date: date = Query(...),
    end_date: date = Query(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
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
    current_user=Depends(get_current_user_dep()),
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
    current_user=Depends(get_current_user_dep()),
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
    current_user=Depends(get_current_user_dep()),
):
    """Calculate current property value."""
    service = PortalHomeValueService(db)
    return service.calculate_current_value(loan_id)


@router.get("/loans/{loan_id}/home-value/dashboard")
def get_home_value_dashboard(
    loan_id: int = Path(..., description="Loan ID"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    """Get complete home value dashboard data."""
    service = PortalHomeValueService(db)
    return service.get_home_value_dashboard(loan_id)


@router.get("/loans/{loan_id}/equity")
def calculate_equity(
    loan_id: int = Path(..., description="Loan ID"),
    current_loan_balance: Decimal = Query(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
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
    current_user=Depends(get_current_user_dep()),
):
    """Calculate potential equity available to unlock."""
    service = PortalHomeValueService(db)
    return service.calculate_equity_unlock(loan_id, current_loan_balance, max_ltv)


@router.get("/loans/{loan_id}/home-value/insights")
def get_home_value_insights(
    loan_id: int = Path(..., description="Loan ID"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    """Get active home value insights."""
    service = PortalHomeValueService(db)
    return service.get_active_insights(loan_id)


@router.post("/loans/{loan_id}/home-value/generate-insights")
def generate_home_value_insights(
    loan_id: int = Path(..., description="Loan ID"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    """Generate home value insights for a loan."""
    service = PortalHomeValueService(db)
    return service.generate_insights(loan_id)


@router.post("/insights/{insight_id}/dismiss")
def dismiss_insight(
    insight_id: int = Path(..., description="Insight ID"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
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
    current_user=Depends(get_current_user_dep()),
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
    current_user=Depends(get_current_user_dep()),
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
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    """Update document status."""
    service = PortalDocumentService(db)
    return service.update_document_status(
        document_id=document_id,
        status=request.status,
        reviewed_by=str(current_user.id),
        rejection_reason=request.rejection_reason,
    )


@router.get("/documents/{document_id}/extraction")
def get_document_extraction(
    document_id: int = Path(..., description="Document ID"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
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
    current_user=Depends(get_current_user_dep()),
):
    """Get document checklist for current lifecycle stage."""
    service = PortalDocumentService(db)
    return service.get_document_checklist(loan_id, lifecycle_stage)


@router.get("/loans/{loan_id}/documents/summary")
def get_document_summary(
    loan_id: int = Path(..., description="Loan ID"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    """Get document upload summary for a loan."""
    service = PortalDocumentService(db)
    return service.get_document_summary(loan_id)


@router.post("/loans/{loan_id}/property-costs")
def set_property_costs(
    loan_id: int = Path(..., description="Loan ID"),
    request: PropertyCostsRequest = Body(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
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
    current_user=Depends(get_current_user_dep()),
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
    current_user=Depends(get_current_user_dep()),
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
    current_user=Depends(get_current_user_dep()),
):
    """Get notification history for a loan."""
    service = PortalNotificationService(db)
    return service.get_notification_history(loan_id, limit)


@router.post("/notifications/process")
def process_notifications(
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    """Process pending notifications in the queue. Requires admin access."""
    require_admin(current_user)
    service = PortalNotificationService(db)
    return service.process_pending_notifications(limit)


@router.get("/notifications/templates")
def get_notification_templates(
    event_type: Optional[str] = Query(None),
    channel: Optional[NotificationChannel] = Query(None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
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
    purl_context: PURLAuthContext = Depends(require_purl_token),
):
    """Get comprehensive borrower dashboard data. Requires PURL token auth."""
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
    purl_context: PURLAuthContext = Depends(require_purl_token),
):
    """Get MUM (Member Until Maturity) servicing dashboard. Requires PURL token auth."""
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


# =============================================================================
# MULTI-LOAN PORTAL SUPPORT - PYDANTIC MODELS
# =============================================================================

from enum import Enum as PyEnum
from sqlalchemy import text
import uuid
import json


class PortalMode(str, PyEnum):
    TRANSACTION = "transaction"
    SERVICING = "servicing"


class PaidOffReason(str, PyEnum):
    REFINANCED = "refinanced"
    SOLD = "sold"
    PAID_IN_FULL = "paid_in_full"
    FORECLOSURE = "foreclosure"
    OTHER = "other"


class LoanSummary(BaseModel):
    """Minimal loan info for selector dropdown"""
    id: int
    loan_number: Optional[str]
    property_address: Optional[str]
    loan_amount: Optional[float]
    status: str
    portal_mode: str
    is_current: bool = False


class LoanPortalView(BaseModel):
    """Complete loan view for portal display"""
    id: int
    loan_number: Optional[str]
    status: str
    portal_mode: str
    loan_purpose: Optional[str]
    product_type: Optional[str]
    loan_amount: Optional[float]
    interest_rate: Optional[float]
    property_address: Optional[dict]
    property_type: Optional[str]
    target_close_date: Optional[str]
    actual_close_date: Optional[str]
    paid_off_date: Optional[str]
    paid_off_reason: Optional[str]
    refinanced_from_loan_id: Optional[int]
    created_at: str
    updated_at: str


class BorrowerPortalContext(BaseModel):
    """Complete portal context for the current borrower session"""
    borrower_profile_id: str
    session_id: str
    current_loan: Optional[dict]
    portal_mode: str
    available_loans: List[dict]
    transaction_loans_count: int
    servicing_loans_count: int
    has_multiple_loans: bool


class SwitchLoanRequest(BaseModel):
    """Request to switch to a different loan"""
    loan_id: int
    reason: Optional[str] = None


class UpdatePortalModeRequest(BaseModel):
    """Request to update loan portal mode (admin only)"""
    portal_mode: PortalMode


class MarkLoanPaidOffRequest(BaseModel):
    """Request to mark a loan as paid off"""
    paid_off_reason: PaidOffReason
    paid_off_date: Optional[datetime] = None
    new_loan_id: Optional[int] = None  # If refinanced, link to new loan


class PortalActivityCreate(BaseModel):
    """Log portal activity"""
    activity_type: str
    activity_data: Optional[dict] = None
    page_path: Optional[str] = None


# =============================================================================
# MULTI-LOAN PORTAL SERVICE
# =============================================================================

class MultiLoanPortalService:
    """Service for managing multi-loan portal context"""

    def __init__(self, db: Session):
        self.db = db

    def get_borrower_loans(
        self,
        borrower_profile_id: str,
        workspace_id: int,
        mode_filter: Optional[PortalMode] = None,
        include_paid_off: bool = False
    ) -> List[dict]:
        """Get all loans for a borrower with optional filtering.
        Note: borrower_profile_id is used for session tracking, loans are fetched by workspace_id.
        """
        query = """
            SELECT
                pl.id, pl.loan_number, pl.status,
                COALESCE(pl.portal_mode, 'transaction') as portal_mode,
                pl.loan_purpose, pl.product_type, pl.loan_amount, pl.interest_rate,
                pl.property_address, pl.property_type,
                pl.target_close_date, pl.actual_close_date,
                pl.paid_off_date, pl.paid_off_reason, pl.refinanced_from_loan_id,
                pl.created_at, pl.updated_at
            FROM purl_loans pl
            WHERE pl.workspace_id = :workspace_id
            AND pl.status NOT IN ('denied', 'cancelled', 'withdrawn')
        """
        params = {
            "workspace_id": workspace_id
        }

        if mode_filter:
            query += " AND COALESCE(pl.portal_mode, 'transaction') = :mode"
            params["mode"] = mode_filter.value

        if not include_paid_off:
            query += " AND pl.paid_off_date IS NULL"

        query += " ORDER BY pl.created_at DESC"

        result = self.db.execute(text(query), params)
        loans = []
        for row in result:
            loan = dict(row._mapping)
            # Parse JSON fields
            if loan.get("property_address") and isinstance(loan["property_address"], str):
                try:
                    loan["property_address"] = json.loads(loan["property_address"])
                except Exception as e:
                    logger.exception(f"Failed to parse property_address JSON: {e}")
            loans.append(loan)

        return loans

    def get_portal_context(
        self,
        borrower_profile_id: str,
        workspace_id: int,
        current_loan_id: Optional[int] = None
    ) -> dict:
        """Get complete portal context for borrower"""
        # Get all loans
        all_loans = self.get_borrower_loans(
            borrower_profile_id,
            workspace_id,
            include_paid_off=True
        )

        # Categorize loans
        transaction_loans = [l for l in all_loans if l.get("portal_mode") == "transaction"]
        servicing_loans = [l for l in all_loans if l.get("portal_mode") == "servicing"]
        active_loans = [l for l in all_loans if l.get("paid_off_date") is None]

        # Determine current loan
        current_loan = None
        if current_loan_id:
            current_loan = next((l for l in all_loans if l["id"] == current_loan_id), None)

        if not current_loan and active_loans:
            # Default to most recent transaction loan, or most recent servicing loan
            current_loan = next(
                (l for l in transaction_loans if l.get("paid_off_date") is None),
                None
            )
            if not current_loan:
                current_loan = next(
                    (l for l in servicing_loans if l.get("paid_off_date") is None),
                    None
                )

        # Build loan summaries
        loan_summaries = []
        for loan in active_loans:
            address = loan.get("property_address")
            if isinstance(address, dict):
                address_str = f"{address.get('street', '')}, {address.get('city', '')} {address.get('state', '')}"
            else:
                address_str = str(address) if address else None

            loan_summaries.append({
                "id": loan["id"],
                "loan_number": loan.get("loan_number"),
                "property_address": address_str,
                "loan_amount": float(loan["loan_amount"]) if loan.get("loan_amount") else None,
                "status": loan["status"],
                "portal_mode": loan.get("portal_mode", "transaction"),
                "is_current": current_loan and loan["id"] == current_loan["id"]
            })

        # Generate session ID
        session_id = str(uuid.uuid4())

        return {
            "borrower_profile_id": borrower_profile_id,
            "session_id": session_id,
            "current_loan": current_loan,
            "portal_mode": current_loan.get("portal_mode", "transaction") if current_loan else "transaction",
            "available_loans": loan_summaries,
            "transaction_loans_count": len([l for l in transaction_loans if l.get("paid_off_date") is None]),
            "servicing_loans_count": len([l for l in servicing_loans if l.get("paid_off_date") is None]),
            "has_multiple_loans": len(active_loans) > 1
        }

    def switch_loan(
        self,
        borrower_profile_id: str,
        workspace_id: int,
        session_id: str,
        from_loan_id: Optional[int],
        to_loan_id: int,
        reason: Optional[str] = None
    ) -> dict:
        """Switch to a different loan and record the switch"""
        # Verify the loan belongs to this borrower
        loans = self.get_borrower_loans(borrower_profile_id, workspace_id, include_paid_off=True)
        to_loan = next((l for l in loans if l["id"] == to_loan_id), None)

        if not to_loan:
            raise HTTPException(status_code=404, detail="Loan not found")

        from_loan = next((l for l in loans if l["id"] == from_loan_id), None) if from_loan_id else None

        # Record the switch
        try:
            self.db.execute(text("""
                INSERT INTO loan_switch_history
                    (session_id, borrower_profile_id, from_loan_id, to_loan_id,
                     from_mode, to_mode, switch_reason)
                VALUES
                    (:session_id, :borrower_profile_id, :from_loan_id, :to_loan_id,
                     :from_mode, :to_mode, :reason)
            """), {
                "session_id": session_id,
                "borrower_profile_id": borrower_profile_id,
                "from_loan_id": from_loan_id,
                "to_loan_id": to_loan_id,
                "from_mode": from_loan.get("portal_mode") if from_loan else None,
                "to_mode": to_loan.get("portal_mode", "transaction"),
                "reason": reason
            })
            self.db.commit()
        except Exception as e:
            # Table might not exist yet, log and continue
            pass

        # Return updated context
        return self.get_portal_context(borrower_profile_id, workspace_id, to_loan_id)

    def create_session(
        self,
        borrower_profile_id: str,
        workspace_id: int,
        loan_id: Optional[int],
        portal_mode: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> str:
        """Create a new portal session"""
        session_id = str(uuid.uuid4())

        try:
            self.db.execute(text("""
                INSERT INTO loan_portal_sessions
                    (session_id, borrower_profile_id, workspace_id, current_loan_id,
                     portal_mode, ip_address, user_agent)
                VALUES
                    (:session_id, :borrower_profile_id, :workspace_id, :loan_id,
                     :portal_mode, :ip_address, :user_agent)
            """), {
                "session_id": session_id,
                "borrower_profile_id": borrower_profile_id,
                "workspace_id": workspace_id,
                "loan_id": loan_id,
                "portal_mode": portal_mode,
                "ip_address": ip_address,
                "user_agent": user_agent
            })
            self.db.commit()
        except Exception as e:
            # Table might not exist yet
            pass

        return session_id

    def log_activity(
        self,
        session_id: str,
        borrower_profile_id: str,
        loan_id: Optional[int],
        activity_type: str,
        activity_data: Optional[dict] = None,
        page_path: Optional[str] = None
    ) -> None:
        """Log portal activity"""
        try:
            self.db.execute(text("""
                INSERT INTO loan_portal_activity
                    (session_id, borrower_profile_id, loan_id, activity_type,
                     activity_data, page_path)
                VALUES
                    (:session_id, :borrower_profile_id, :loan_id, :activity_type,
                     :activity_data, :page_path)
            """), {
                "session_id": session_id,
                "borrower_profile_id": borrower_profile_id,
                "loan_id": loan_id,
                "activity_type": activity_type,
                "activity_data": json.dumps(activity_data) if activity_data else None,
                "page_path": page_path
            })
            self.db.commit()
        except Exception as e:
            # Table might not exist yet
            pass


# =============================================================================
# MULTI-LOAN LIFECYCLE SERVICE
# =============================================================================

class MultiLoanLifecycleService:
    """Service for managing loan lifecycle transitions"""

    def __init__(self, db: Session):
        self.db = db

    def transition_to_servicing(self, loan_id: int) -> dict:
        """Transition a loan from transaction to servicing mode"""
        result = self.db.execute(text("""
            SELECT id, status, COALESCE(portal_mode, 'transaction') as portal_mode, actual_close_date
            FROM purl_loans WHERE id = :loan_id
        """), {"loan_id": loan_id})

        loan = result.fetchone()
        if not loan:
            raise HTTPException(status_code=404, detail="Loan not found")

        if loan.portal_mode == "servicing":
            return {"message": "Loan already in servicing mode", "loan_id": loan_id}

        if loan.status != "closed" or not loan.actual_close_date:
            raise HTTPException(
                status_code=400,
                detail="Loan must be closed before transitioning to servicing"
            )

        self.db.execute(text("""
            UPDATE purl_loans
            SET portal_mode = 'servicing', updated_at = CURRENT_TIMESTAMP
            WHERE id = :loan_id
        """), {"loan_id": loan_id})

        self.db.commit()

        return {
            "message": "Loan transitioned to servicing mode",
            "loan_id": loan_id,
            "new_mode": "servicing"
        }

    def mark_paid_off(
        self,
        loan_id: int,
        reason: PaidOffReason,
        paid_off_date: Optional[datetime] = None,
        new_loan_id: Optional[int] = None
    ) -> dict:
        """Mark a loan as paid off"""
        result = self.db.execute(text("""
            SELECT id, status, COALESCE(portal_mode, 'transaction') as portal_mode
            FROM purl_loans WHERE id = :loan_id
        """), {"loan_id": loan_id})

        loan = result.fetchone()
        if not loan:
            raise HTTPException(status_code=404, detail="Loan not found")

        if loan.portal_mode != "servicing":
            raise HTTPException(
                status_code=400,
                detail="Only servicing loans can be marked as paid off"
            )

        self.db.execute(text("""
            UPDATE purl_loans
            SET paid_off_date = :paid_off_date,
                paid_off_reason = :reason,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :loan_id
        """), {
            "loan_id": loan_id,
            "paid_off_date": paid_off_date or datetime.now(),
            "reason": reason.value
        })

        if reason == PaidOffReason.REFINANCED and new_loan_id:
            self.db.execute(text("""
                UPDATE purl_loans
                SET refinanced_from_loan_id = :old_loan_id
                WHERE id = :new_loan_id
            """), {"old_loan_id": loan_id, "new_loan_id": new_loan_id})

        self.db.commit()

        return {
            "message": "Loan marked as paid off",
            "loan_id": loan_id,
            "reason": reason.value,
            "paid_off_date": (paid_off_date or datetime.now()).isoformat()
        }

    def get_loan_history(self, loan_id: int) -> List[dict]:
        """Get the chain of loans (refinance history)"""
        history = []

        result = self.db.execute(text("""
            SELECT id, loan_number, loan_amount, status,
                   COALESCE(portal_mode, 'transaction') as portal_mode,
                   actual_close_date, paid_off_date, paid_off_reason,
                   refinanced_from_loan_id
            FROM purl_loans WHERE id = :loan_id
        """), {"loan_id": loan_id})

        current = result.fetchone()
        if not current:
            return history

        history.append(dict(current._mapping))

        while current and current.refinanced_from_loan_id:
            result = self.db.execute(text("""
                SELECT id, loan_number, loan_amount, status,
                       COALESCE(portal_mode, 'transaction') as portal_mode,
                       actual_close_date, paid_off_date, paid_off_reason,
                       refinanced_from_loan_id
                FROM purl_loans WHERE id = :loan_id
            """), {"loan_id": current.refinanced_from_loan_id})

            current = result.fetchone()
            if current:
                history.append(dict(current._mapping))

        return history


# =============================================================================
# PORTAL ACCESS BY TOKEN (Magic Link Entry Point)
# =============================================================================

@router.get("/access/{token}")
def get_portal_by_token(
    token: str = Path(..., description="PURL access token"),
    db: Session = Depends(get_db),
):
    """Get portal data using a PURL access token.

    This is the entry point for magic link access to the borrower portal.
    Validates the token and returns portal data including loan information.
    """
    from services.purl_token_service import PURLTokenService
    from sqlalchemy import text

    # Validate token format
    if not token.startswith("purl_live_"):
        raise HTTPException(
            status_code=401,
            detail="Invalid token format"
        )

    # Verify token and get context
    token_service = PURLTokenService(db)
    context = token_service.verify_token(token)

    if not context:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired access token"
        )

    workspace_id = context["workspace_id"]
    contact_id = context.get("contact_id")
    token_id = context["token_id"]

    # Get the primary/current loan for this workspace
    loan_result = db.execute(text("""
        SELECT
            l.id as loan_id,
            l.loan_number,
            l.status,
            l.loan_purpose,
            l.product_type,
            l.loan_amount,
            l.property_address,
            l.property_type,
            l.target_close_date,
            l.actual_close_date,
            l.paid_off_date,
            CASE
                WHEN l.paid_off_date IS NOT NULL THEN 'servicing'
                WHEN l.actual_close_date IS NOT NULL THEN 'servicing'
                ELSE 'transaction'
            END as portal_mode
        FROM purl_loans l
        WHERE l.workspace_id = :workspace_id
        AND l.paid_off_date IS NULL
        ORDER BY l.created_at DESC
        LIMIT 1
    """), {"workspace_id": workspace_id})

    loan_row = loan_result.fetchone()

    if not loan_row:
        raise HTTPException(
            status_code=404,
            detail="No active loan found for this portal"
        )

    loan_data = dict(loan_row._mapping)

    # Get borrower name from contact or workspace
    borrower_name = None
    if contact_id:
        contact_result = db.execute(text("""
            SELECT first_name, last_name, email
            FROM purl_contacts
            WHERE id = :contact_id
        """), {"contact_id": contact_id})
        contact = contact_result.fetchone()
        if contact:
            borrower_name = f"{contact.first_name or ''} {contact.last_name or ''}".strip()

    if not borrower_name:
        # Try to get from workspace
        workspace_result = db.execute(text("""
            SELECT display_name FROM purl_workspaces WHERE id = :workspace_id
        """), {"workspace_id": workspace_id})
        workspace = workspace_result.fetchone()
        if workspace:
            borrower_name = workspace.display_name

    # Determine lifecycle stage based on loan status
    lifecycle_stage = "ACTIVE"
    if loan_data.get("paid_off_date"):
        lifecycle_stage = "MUM"
    elif loan_data.get("actual_close_date"):
        lifecycle_stage = "MUM"
    elif loan_data.get("status") in ["funded", "closed"]:
        lifecycle_stage = "MUM"

    # Parse property address if it's a JSON string
    property_address = loan_data.get("property_address")
    if isinstance(property_address, str):
        try:
            import json
            property_address = json.loads(property_address)
        except Exception as e:
            logger.exception(f"Failed to parse property_address JSON string: {e}")

    return {
        "loan_id": loan_data["loan_id"],
        "loan_number": loan_data.get("loan_number"),
        "borrower_name": borrower_name or "Borrower",
        "workspace_id": workspace_id,
        "purl_token": token,
        "lifecycle": {
            "stage": lifecycle_stage,
            "status": loan_data.get("status", "processing"),
        },
        "loan": {
            "id": loan_data["loan_id"],
            "loan_number": loan_data.get("loan_number"),
            "status": loan_data.get("status"),
            "portal_mode": loan_data.get("portal_mode", "transaction"),
            "loan_purpose": loan_data.get("loan_purpose"),
            "product_type": loan_data.get("product_type"),
            "loan_amount": float(loan_data["loan_amount"]) if loan_data.get("loan_amount") else None,
            "property_address": property_address,
            "property_type": loan_data.get("property_type"),
        }
    }


# =============================================================================
# MULTI-LOAN PORTAL API ENDPOINTS
# =============================================================================

@router.get("/multi-loan/context")
def get_multi_loan_context(
    request: Request,
    loan_id: Optional[int] = Query(None, description="Current loan ID"),
    db: Session = Depends(get_db),
    purl_context: PURLAuthContext = Depends(require_purl_token),
):
    """Get the current borrower's multi-loan portal context.

    Requires valid PURL token authentication. The workspace_id and borrower identity
    are derived from the authenticated token.
    """
    # Use workspace_id from authenticated context
    workspace_id = purl_context.workspace_id
    # Use contact_id as borrower_profile_id (or token_id if no contact)
    borrower_profile_id = str(purl_context.contact_id or purl_context.token_id)

    service = MultiLoanPortalService(db)
    context = service.get_portal_context(borrower_profile_id, workspace_id, loan_id)

    # Create session
    session_id = service.create_session(
        borrower_profile_id=borrower_profile_id,
        workspace_id=workspace_id,
        loan_id=context.get("current_loan", {}).get("id") if context.get("current_loan") else None,
        portal_mode=context.get("portal_mode", "transaction"),
        ip_address=request.client.host if request and request.client else None,
        user_agent=request.headers.get("user-agent") if request else None
    )

    context["session_id"] = session_id

    return context


@router.get("/multi-loan/loans")
def get_multi_loan_borrower_loans(
    mode: Optional[PortalMode] = Query(None, description="Filter by portal mode"),
    include_paid_off: bool = Query(False, description="Include paid off loans"),
    db: Session = Depends(get_db),
    purl_context: PURLAuthContext = Depends(require_purl_token),
):
    """Get all loans for a borrower.

    Requires valid PURL token authentication. The workspace_id and borrower identity
    are derived from the authenticated token.
    """
    workspace_id = purl_context.workspace_id
    borrower_profile_id = str(purl_context.contact_id or purl_context.token_id)

    service = MultiLoanPortalService(db)
    loans = service.get_borrower_loans(
        borrower_profile_id,
        workspace_id,
        mode_filter=mode,
        include_paid_off=include_paid_off
    )

    return {"loans": loans, "count": len(loans)}


@router.post("/multi-loan/loans/switch")
def switch_multi_loan(
    switch_request: SwitchLoanRequest,
    session_id: str = Query(..., description="Current session ID"),
    current_loan_id: Optional[int] = Query(None, description="Current loan ID"),
    db: Session = Depends(get_db),
    purl_context: PURLAuthContext = Depends(require_purl_token),
):
    """Switch to a different loan.

    Requires valid PURL token authentication. The workspace_id and borrower identity
    are derived from the authenticated token.
    """
    workspace_id = purl_context.workspace_id
    borrower_profile_id = str(purl_context.contact_id or purl_context.token_id)

    service = MultiLoanPortalService(db)
    context = service.switch_loan(
        borrower_profile_id=borrower_profile_id,
        workspace_id=workspace_id,
        session_id=session_id,
        from_loan_id=current_loan_id,
        to_loan_id=switch_request.loan_id,
        reason=switch_request.reason
    )

    return {
        "success": True,
        "previous_loan_id": current_loan_id,
        "new_loan_id": switch_request.loan_id,
        "new_portal_mode": context.get("portal_mode"),
        "context": context
    }


@router.get("/multi-loan/loans/{loan_id}/history")
def get_multi_loan_history(
    loan_id: int = Path(..., description="Loan ID"),
    db: Session = Depends(get_db),
    purl_context: PURLAuthContext = Depends(require_purl_token),
):
    """Get the loan refinance history chain.

    Requires valid PURL token authentication. Validates that the requested loan
    belongs to the authenticated borrower's workspace.
    """
    workspace_id = purl_context.workspace_id
    borrower_profile_id = str(purl_context.contact_id or purl_context.token_id)

    # Verify the loan belongs to this borrower's workspace
    portal_service = MultiLoanPortalService(db)
    borrower_loans = portal_service.get_borrower_loans(
        borrower_profile_id, workspace_id, include_paid_off=True
    )
    loan_ids = [loan["id"] for loan in borrower_loans]

    if loan_id not in loan_ids:
        raise HTTPException(
            status_code=403,
            detail="Access denied. This loan does not belong to your account."
        )

    lifecycle_service = MultiLoanLifecycleService(db)
    history = lifecycle_service.get_loan_history(loan_id)

    return {"loan_id": loan_id, "history": history}


@router.post("/multi-loan/admin/loans/{loan_id}/transition-to-servicing")
async def admin_multi_loan_transition_to_servicing(
    loan_id: int = Path(..., description="Loan ID"),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep()),
):
    """Admin endpoint to transition a loan to servicing mode.

    Requires admin authentication and authorization.
    """
    require_admin(current_user)

    lifecycle_service = MultiLoanLifecycleService(db)
    result = lifecycle_service.transition_to_servicing(loan_id)

    return result


@router.post("/multi-loan/admin/loans/{loan_id}/mark-paid-off")
async def admin_multi_loan_mark_paid_off(
    loan_id: int = Path(..., description="Loan ID"),
    request: MarkLoanPaidOffRequest = Body(...),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep()),
):
    """Admin endpoint to mark a loan as paid off.

    Requires admin authentication and authorization.
    """
    require_admin(current_user)

    lifecycle_service = MultiLoanLifecycleService(db)
    result = lifecycle_service.mark_paid_off(
        loan_id=loan_id,
        reason=request.paid_off_reason,
        paid_off_date=request.paid_off_date,
        new_loan_id=request.new_loan_id
    )

    return result


@router.put("/multi-loan/admin/loans/{loan_id}/portal-mode")
async def admin_update_multi_loan_portal_mode(
    loan_id: int = Path(..., description="Loan ID"),
    request: UpdatePortalModeRequest = Body(...),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep()),
):
    """Admin endpoint to update loan portal mode.

    Requires admin authentication and authorization.
    """
    require_admin(current_user)

    db.execute(text("""
        UPDATE purl_loans
        SET portal_mode = :mode, updated_at = CURRENT_TIMESTAMP
        WHERE id = :loan_id
    """), {"loan_id": loan_id, "mode": request.portal_mode.value})

    db.commit()

    return {"message": "Portal mode updated", "loan_id": loan_id, "portal_mode": request.portal_mode.value}


@router.post("/multi-loan/activity")
def log_multi_loan_portal_activity(
    activity: PortalActivityCreate,
    session_id: str = Query(..., description="Current session ID"),
    loan_id: Optional[int] = Query(None, description="Current loan ID"),
    db: Session = Depends(get_db),
    purl_context: PURLAuthContext = Depends(require_purl_token),
):
    """Log portal activity for analytics.

    Requires valid PURL token authentication. The borrower identity
    is derived from the authenticated token.
    """
    borrower_profile_id = str(purl_context.contact_id or purl_context.token_id)

    service = MultiLoanPortalService(db)
    service.log_activity(
        session_id=session_id,
        borrower_profile_id=borrower_profile_id,
        loan_id=loan_id,
        activity_type=activity.activity_type,
        activity_data=activity.activity_data,
        page_path=activity.page_path
    )

    return {"success": True}


# =============================================================================
# LOAN ID TO PORTAL LOOKUP ENDPOINT
# =============================================================================

@router.get("/by-loan/{loan_id}")
def get_portal_by_loan_id(
    loan_id: int = Path(..., description="Loan ID (either portal_loans.id or crm_deal_id)"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    """Look up portal access by loan ID.

    This endpoint maps a loan ID to the portal, supporting both:
    - portal_loans.id (the portal loan ID)
    - portal_loans.crm_deal_id (the CRM deal ID)

    Returns portal access information for redirecting to the borrower portal.
    Requires LO authentication since it returns access tokens.
    """
    from models.portal_models import PortalLoan
    from services.purl_token_service import PURLTokenService
    from sqlalchemy import text
    import logging

    logger = logging.getLogger(__name__)

    try:
        # Try to find portal loan by ID first, then by crm_deal_id
        portal_loan = db.query(PortalLoan).filter(PortalLoan.id == loan_id).first()

        if not portal_loan:
            portal_loan = db.query(PortalLoan).filter(PortalLoan.crm_deal_id == loan_id).first()
    except Exception as e:
        logger.error(f"Error querying PortalLoan: {e}")
        db.rollback()  # Reset transaction after error
        portal_loan = None

    if not portal_loan:
        # Try looking up in purl_loans table if PortalLoan is empty
        try:
            result = db.execute(text("""
                SELECT id, loan_number, status, workspace_id, property_address,
                       loan_amount, target_close_date, actual_close_date
                FROM purl_loans
                WHERE id = :loan_id
                LIMIT 1
            """), {"loan_id": loan_id})
            purl_loan = result.fetchone()
        except Exception as e:
            logger.error(f"Error querying purl_loans: {e}")
            db.rollback()
            purl_loan = None

        if purl_loan:
            loan_data = dict(purl_loan._mapping)
            workspace_id = loan_data.get("workspace_id")

            # Get access token for this workspace
            access_token = None
            try:
                token_result = db.execute(text("""
                    SELECT token FROM purl_access_tokens
                    WHERE workspace_id = :workspace_id
                    AND is_active = true
                    AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
                    ORDER BY created_at DESC
                    LIMIT 1
                """), {"workspace_id": workspace_id})
                token_row = token_result.fetchone()
                access_token = token_row.token if token_row else None
            except Exception as e:
                logger.error(f"Error fetching access token: {e}")

            return {
                "found": True,
                "portal_loan_id": loan_data["id"],
                "loan_number": loan_data.get("loan_number"),
                "status": loan_data.get("status"),
                "access_token": access_token,
                "redirect_url": f"/borrower-portal/{access_token}" if access_token else None,
                "property_address": loan_data.get("property_address"),
                "loan_amount": float(loan_data["loan_amount"]) if loan_data.get("loan_amount") else None,
            }

        # No loan found in any table
        raise HTTPException(status_code=404, detail="Loan not found")

    # Found in portal_loans table
    # Get workspace_id from portal_loan if available
    workspace_id = getattr(portal_loan, 'workspace_id', None)

    # Try to find an access token for this portal
    access_token = None
    try:
        token_result = db.execute(text("""
            SELECT token FROM purl_access_tokens
            WHERE loan_id = :loan_id OR workspace_id = :workspace_id
            AND is_active = true
            AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
            ORDER BY created_at DESC
            LIMIT 1
        """), {"loan_id": portal_loan.id, "workspace_id": workspace_id})
        token_row = token_result.fetchone()
        access_token = token_row.token if token_row else None
    except Exception as e:
        logger.error(f"Error fetching portal_loan access token: {e}")

    return {
        "found": True,
        "portal_loan_id": portal_loan.id,
        "crm_deal_id": portal_loan.crm_deal_id,
        "loan_number": getattr(portal_loan, 'loan_number', None),
        "status": getattr(portal_loan, 'status', None),
        "lifecycle_stage": portal_loan.lifecycle_stage.value if portal_loan.lifecycle_stage else None,
        "access_token": access_token,
        "redirect_url": f"/borrower-portal/{access_token}" if access_token else None,
        "portal_enabled": portal_loan.portal_enabled,
        "partner_portal_enabled": portal_loan.partner_portal_enabled,
    }