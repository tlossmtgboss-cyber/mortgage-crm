"""
Compliance-Aware Scheduling Routes
====================================

Endpoints that evaluate loans against TRID, lock expiration, SLA, and condition
rules, then surface required appointments.  This is the scheduler feature that
ties regulatory deadlines directly to the LO's calendar.

Endpoints:
  GET  /compliance/evaluate/{loan_id}   Evaluate one loan
  GET  /compliance/pipeline             Evaluate all active loans for the org
  POST /compliance/schedule/{loan_id}   Create a compliance appointment
  GET  /compliance/overdue              List overdue compliance appointments

All endpoints require authentication and organization context.
"""

from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from typing import Any, Dict, List, Optional
import logging

from db import get_db
from routes.scheduler._helpers import (
    get_current_user,
    _get_org_id,
    _is_scheduler_admin,
)
from services.compliance_scheduling_service import ComplianceSchedulingService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/compliance", tags=["Compliance Scheduling"])


# =============================================================================
# PYDANTIC MODELS
# =============================================================================

class ComplianceSuggestion(BaseModel):
    """A single compliance appointment suggestion."""
    rule_id: str
    appointment_type: str
    meeting_type: str
    duration_minutes: int
    urgency: str
    reason: str
    regulation: str
    loan_id: int
    loan_number: Optional[str] = None
    borrower_name: Optional[str] = None
    loan_stage: Optional[str] = None
    lo_id: Optional[int] = None
    context: Dict[str, Any] = Field(default_factory=dict)
    days_remaining: int = 0


class LoanEvaluationResponse(BaseModel):
    """Response from evaluating a single loan."""
    loan_id: int
    suggestions: List[ComplianceSuggestion]
    suggestion_count: int
    critical_count: int
    high_count: int


class PipelineEvaluationResponse(BaseModel):
    """Response from evaluating the full pipeline."""
    organization_id: int
    total_loans_evaluated: int
    total_suggestions: int
    critical_count: int
    high_count: int
    medium_count: int
    suggestions: List[ComplianceSuggestion]


class ScheduleComplianceRequest(BaseModel):
    """Request to create a compliance appointment."""
    rule_id: str
    scheduled_start: Optional[datetime] = None
    notes: Optional[str] = None


class ComplianceAppointmentResponse(BaseModel):
    """Response after creating a compliance appointment."""
    appointment_id: int
    loan_id: int
    loan_number: Optional[str] = None
    borrower_name: Optional[str] = None
    rule_id: str
    appointment_type: str
    urgency: str
    regulation: str
    scheduled_start: str
    scheduled_end: str
    duration_minutes: int
    status: str


class OverdueAppointment(BaseModel):
    """An overdue compliance appointment."""
    appointment_id: int
    title: Optional[str] = None
    loan_id: Optional[int] = None
    rule_id: Optional[str] = None
    urgency: Optional[str] = None
    regulation: Optional[str] = None
    scheduled_start: str
    hours_overdue: float
    assigned_user_id: Optional[int] = None
    attendee_name: Optional[str] = None
    status: str


class OverdueResponse(BaseModel):
    """Response listing overdue compliance appointments."""
    organization_id: int
    overdue_count: int
    appointments: List[OverdueAppointment]


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.get(
    "/evaluate/{loan_id}",
    response_model=LoanEvaluationResponse,
    summary="Evaluate compliance scheduling for one loan",
    description=(
        "Checks a single loan against all compliance rules (TRID disclosure timing, "
        "lock expirations, CD acknowledgment, outstanding conditions, appraisal gaps, "
        "SLA breaches) and returns required appointment suggestions."
    ),
)
async def evaluate_loan(
    loan_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    org_id = _get_org_id(current_user)

    service = ComplianceSchedulingService(db)
    suggestions = await service.evaluate_loan(loan_id, org_id)

    critical = sum(1 for s in suggestions if s.get("urgency") == "critical")
    high = sum(1 for s in suggestions if s.get("urgency") == "high")

    return LoanEvaluationResponse(
        loan_id=loan_id,
        suggestions=suggestions,
        suggestion_count=len(suggestions),
        critical_count=critical,
        high_count=high,
    )


@router.get(
    "/pipeline",
    response_model=PipelineEvaluationResponse,
    summary="Evaluate compliance scheduling for all active loans",
    description=(
        "Scans the entire active pipeline (or a single LO's pipeline) and returns "
        "all compliance-required appointments sorted by urgency. This powers the "
        "Compliance Calendar Dashboard."
    ),
)
async def evaluate_pipeline(
    request: Request,
    lo_id: Optional[int] = Query(None, description="Filter to a specific loan officer"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    org_id = _get_org_id(current_user)

    # Non-admins can only see their own pipeline
    user_id = getattr(current_user, "id", None)
    if not _is_scheduler_admin(current_user) and lo_id and lo_id != user_id:
        raise HTTPException(status_code=403, detail="Cannot view another officer's compliance pipeline")

    effective_lo_id = lo_id
    if not _is_scheduler_admin(current_user) and lo_id is None:
        effective_lo_id = user_id

    service = ComplianceSchedulingService(db)
    suggestions = await service.evaluate_pipeline(org_id, lo_id=effective_lo_id)

    # Count total loans evaluated (unique loan_ids in suggestions)
    evaluated_loan_ids = set()
    from database.models.lead_loan import Loan
    loan_query = db.query(Loan.id).filter(
        Loan.organization_id == org_id,
        ~Loan.stage.in_(("FUNDED", "CANCELLED", "DENIED", "DEAD", "WITHDRAWN", "DOES_NOT_QUALIFY")),
    )
    if effective_lo_id:
        loan_query = loan_query.filter(Loan.loan_officer_id == effective_lo_id)
    total_loans = loan_query.count()

    critical = sum(1 for s in suggestions if s.get("urgency") == "critical")
    high = sum(1 for s in suggestions if s.get("urgency") == "high")
    medium = sum(1 for s in suggestions if s.get("urgency") == "medium")

    return PipelineEvaluationResponse(
        organization_id=org_id,
        total_loans_evaluated=total_loans,
        total_suggestions=len(suggestions),
        critical_count=critical,
        high_count=high,
        medium_count=medium,
        suggestions=suggestions,
    )


@router.post(
    "/schedule/{loan_id}",
    response_model=ComplianceAppointmentResponse,
    summary="Create a compliance-required appointment",
    description=(
        "Creates an appointment tied to a specific compliance rule for a loan. "
        "The appointment includes full audit context (rule ID, regulation, reason) "
        "and creates a corresponding compliance alert for the audit trail."
    ),
)
async def schedule_compliance_appointment(
    loan_id: int,
    body: ScheduleComplianceRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    org_id = _get_org_id(current_user)

    service = ComplianceSchedulingService(db)

    try:
        result = await service.create_compliance_appointment(
            loan_id=loan_id,
            rule_id=body.rule_id,
            user=current_user,
            organization_id=org_id,
            scheduled_start=body.scheduled_start,
            notes=body.notes,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    return ComplianceAppointmentResponse(**result)


@router.get(
    "/overdue",
    response_model=OverdueResponse,
    summary="List overdue compliance appointments",
    description=(
        "Returns compliance appointments that were scheduled but have passed "
        "their start time without being completed. These represent regulatory "
        "risk items requiring immediate attention."
    ),
)
async def list_overdue_compliance(
    request: Request,
    lo_id: Optional[int] = Query(None, description="Filter to a specific loan officer"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    org_id = _get_org_id(current_user)

    # Non-admins can only see their own overdue items
    user_id = getattr(current_user, "id", None)
    if not _is_scheduler_admin(current_user) and lo_id and lo_id != user_id:
        raise HTTPException(status_code=403, detail="Cannot view another officer's overdue appointments")

    effective_lo_id = lo_id
    if not _is_scheduler_admin(current_user) and lo_id is None:
        effective_lo_id = user_id

    service = ComplianceSchedulingService(db)
    overdue = await service.get_overdue_compliance_appointments(org_id, lo_id=effective_lo_id)

    return OverdueResponse(
        organization_id=org_id,
        overdue_count=len(overdue),
        appointments=overdue,
    )
