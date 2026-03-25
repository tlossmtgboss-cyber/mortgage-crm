"""
Scheduler Today Summary - Aggregated LO "Today" view in a single API call.

Endpoints:
  - GET /today-summary    All data the LO Today view needs (appointments, tasks, leads, SLA alerts)

Replaces 4 separate frontend calls with a single aggregated response.
All four queries are lightweight (indexed, bounded) and run sequentially
within a single DB session for thread safety.
"""

from datetime import datetime, time, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, cast, String
from typing import List, Optional
import logging

from db import get_db
from routes.scheduler._helpers import (
    get_current_user, get_models, _get_org_id,
)
from smart_scheduler_models import AppointmentStatus

logger = logging.getLogger(__name__)

router = APIRouter()


# =============================================================================
# CONSTANTS
# =============================================================================

# SLA targets in days for stage-to-stage transitions
SLA_TARGETS = {
    "APPLICATION_to_DISCLOSED": 3,
    "DISCLOSED_to_SUBMITTED": 7,
    "SUBMITTED_to_UW_RECEIVED": 2,
    "UW_RECEIVED_to_APPROVED": 5,
    "APPROVED_to_CLEAR_TO_CLOSE": 3,
    "CLEAR_TO_CLOSE_to_DOCS_OUT": 3,
    "DOCS_OUT_to_FUNDED": 5,
}

# Closed/terminal stages excluded from active pipeline queries
TERMINAL_STAGES = (
    "FUNDED", "CANCELLED", "DENIED", "DEAD", "WITHDRAWN", "DOES_NOT_QUALIFY"
)

# Map each active stage to its SLA target (days allowed in that stage)
_STAGE_SLA_DAYS = {}
for key, days in SLA_TARGETS.items():
    from_stage = key.split("_to_")[0]
    _STAGE_SLA_DAYS[from_stage] = days


# =============================================================================
# PYDANTIC RESPONSE MODELS
# =============================================================================

class AppointmentSummaryItem(BaseModel):
    """A single appointment in the today summary."""
    id: int
    title: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    client_name: Optional[str] = None
    type: Optional[str] = None
    status: Optional[str] = None
    meeting_mode: Optional[str] = None
    video_link: Optional[str] = None
    lead_id: Optional[int] = None
    loan_id: Optional[int] = None


class AppointmentsSection(BaseModel):
    """Appointments section of the today summary."""
    count: int = 0
    next_appointment: Optional[AppointmentSummaryItem] = None
    items: List[AppointmentSummaryItem] = Field(default_factory=list)


class TaskSummaryItem(BaseModel):
    """A single task in the today summary."""
    id: int
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    due_date: Optional[str] = None
    is_overdue: bool = False
    related_contact_name: Optional[str] = None
    lead_id: Optional[int] = None
    loan_id: Optional[int] = None


class TasksSection(BaseModel):
    """Tasks section of the today summary."""
    due_today: int = 0
    overdue: int = 0
    items: List[TaskSummaryItem] = Field(default_factory=list)


class LeadFollowUpItem(BaseModel):
    """A single lead needing follow-up."""
    id: int
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    stage: Optional[str] = None
    last_contact: Optional[str] = None
    days_since_contact: Optional[int] = None
    ai_score: Optional[int] = None


class LeadsSection(BaseModel):
    """Leads section of the today summary."""
    need_follow_up: int = 0
    items: List[LeadFollowUpItem] = Field(default_factory=list)


class SLAAlertItem(BaseModel):
    """A single SLA alert for a loan."""
    loan_id: int
    loan_number: Optional[str] = None
    borrower_name: Optional[str] = None
    stage: Optional[str] = None
    days_in_stage: int = 0
    sla_target_days: int = 0
    days_over_sla: int = 0
    severity: str = "warning"  # "warning" or "critical"


class SLAAlertsSection(BaseModel):
    """SLA alerts section of the today summary."""
    total: int = 0
    critical: int = 0
    items: List[SLAAlertItem] = Field(default_factory=list)


class TodaySummaryResponse(BaseModel):
    """Aggregated today summary response for the LO dashboard."""
    appointments: AppointmentsSection = Field(default_factory=AppointmentsSection)
    tasks: TasksSection = Field(default_factory=TasksSection)
    leads: LeadsSection = Field(default_factory=LeadsSection)
    sla_alerts: SLAAlertsSection = Field(default_factory=SLAAlertsSection)
    generated_at: str = Field(..., description="ISO 8601 timestamp of when this summary was generated")

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# QUERY HELPERS (each returns its section)
# =============================================================================

def _fetch_today_appointments(db: Session, models: dict, user_id: int, org_id: int, now: datetime) -> AppointmentsSection:
    """Fetch today's appointments for the user."""
    Appointment = models.get("Appointment")
    if not Appointment:
        return AppointmentsSection()

    today_start = datetime.combine(now.date(), time.min)
    today_end = datetime.combine(now.date(), time.max)

    appointments = (
        db.query(Appointment)
        .filter(
            Appointment.organization_id == org_id,
            or_(
                Appointment.assigned_user_id == user_id,
                Appointment.created_by_user_id == user_id,
            ),
            Appointment.scheduled_start >= today_start,
            Appointment.scheduled_start <= today_end,
            Appointment.status.notin_([AppointmentStatus.CANCELLED, AppointmentStatus.RESCHEDULED]),
        )
        .order_by(Appointment.scheduled_start.asc())
        .all()
    )

    items = []
    for a in appointments:
        items.append(AppointmentSummaryItem(
            id=a.id,
            title=a.title,
            start_time=a.scheduled_start.isoformat() if a.scheduled_start else None,
            end_time=a.scheduled_end.isoformat() if a.scheduled_end else None,
            client_name=a.attendee_name,
            type=a.meeting_type.value if a.meeting_type else None,
            status=a.status.value if a.status else None,
            meeting_mode=a.meeting_mode.value if a.meeting_mode else None,
            video_link=a.video_link,
            lead_id=a.lead_id,
            loan_id=a.loan_id,
        ))

    # Find next upcoming appointment (hasn't started yet)
    next_appt = None
    for item in items:
        if item.start_time and item.start_time > now.isoformat():
            next_appt = item
            break

    return AppointmentsSection(
        count=len(items),
        next_appointment=next_appt,
        items=items,
    )


def _fetch_today_tasks(db: Session, user_id: int, org_id: int, now: datetime) -> TasksSection:
    """Fetch tasks due today or overdue for the user."""
    from database.models.task import Task

    today_start = datetime.combine(now.date(), time.min)
    today_end = datetime.combine(now.date(), time.max)

    tasks = (
        db.query(Task)
        .filter(
            Task.organization_id == org_id,
            Task.owner_id == user_id,
            Task.status.notin_(["completed", "cancelled"]),
            or_(
                # Due today
                and_(Task.due_date >= today_start, Task.due_date <= today_end),
                # Overdue
                Task.due_date < today_start,
            ),
        )
        .order_by(Task.due_date.asc().nullslast())
        .limit(20)
        .all()
    )

    items = []
    overdue_count = 0
    due_today_count = 0

    for t in tasks:
        is_overdue = bool(t.due_date and t.due_date < today_start)
        if is_overdue:
            overdue_count += 1
        else:
            due_today_count += 1

        items.append(TaskSummaryItem(
            id=t.id,
            title=t.title,
            description=(t.description or "")[:200] if t.description else None,
            status=t.status,
            priority=t.priority,
            due_date=t.due_date.isoformat() if t.due_date else None,
            is_overdue=is_overdue,
            related_contact_name=t.related_contact_name,
            lead_id=t.lead_id,
            loan_id=t.loan_id,
        ))

    return TasksSection(
        due_today=due_today_count,
        overdue=overdue_count,
        items=items,
    )


def _fetch_leads_needing_followup(db: Session, user_id: int, org_id: int, now: datetime) -> LeadsSection:
    """Fetch leads with no contact in 3+ days assigned to the user."""
    from database.models.lead_loan import Lead

    stale_threshold = now - timedelta(days=3)

    leads = (
        db.query(Lead)
        .filter(
            Lead.organization_id == org_id,
            Lead.owner_id == user_id,
            Lead.stage.notin_(["Closed", "Funded", "Dead", "Withdrawn", "Lost"]),
            or_(
                Lead.last_contact < stale_threshold,
                Lead.last_contact.is_(None),
            ),
        )
        .order_by(Lead.last_contact.asc().nullsfirst())
        .limit(15)
        .all()
    )

    items = []
    for lead in leads:
        days_since = None
        if lead.last_contact:
            delta = now - lead.last_contact
            days_since = delta.days

        items.append(LeadFollowUpItem(
            id=lead.id,
            name=lead.name,
            email=lead.email,
            phone=lead.phone,
            stage=lead.stage,
            last_contact=lead.last_contact.isoformat() if lead.last_contact else None,
            days_since_contact=days_since,
            ai_score=lead.ai_score,
        ))

    return LeadsSection(
        need_follow_up=len(items),
        items=items,
    )


def _fetch_sla_alerts(db: Session, user_id: int, org_id: int, now: datetime) -> SLAAlertsSection:
    """Fetch loans approaching or past SLA targets for the user."""
    from database.models.lead_loan import Loan

    loans = (
        db.query(Loan)
        .filter(
            Loan.organization_id == org_id,
            Loan.loan_officer_id == user_id,
            cast(Loan.stage, String).notin_(TERMINAL_STAGES),
            Loan.stage_changed_at.isnot(None),
        )
        .all()
    )

    items = []
    for loan in loans:
        stage = loan.stage or ""
        sla_target = _STAGE_SLA_DAYS.get(stage)
        if sla_target is None:
            # No SLA target defined for this stage, skip
            continue

        days_in_stage = (now - loan.stage_changed_at).days if loan.stage_changed_at else 0
        days_over = days_in_stage - sla_target

        # Only include loans that are approaching SLA (within 1 day) or past SLA
        if days_over < -1:
            continue

        if days_over >= sla_target:
            severity = "critical"  # Over 2x the target
        elif days_over >= 0:
            severity = "warning"
        else:
            severity = "warning"  # Approaching (within 1 day)

        items.append(SLAAlertItem(
            loan_id=loan.id,
            loan_number=loan.loan_number,
            borrower_name=loan.borrower_name,
            stage=stage,
            days_in_stage=days_in_stage,
            sla_target_days=sla_target,
            days_over_sla=max(days_over, 0),
            severity=severity,
        ))

    # Sort: critical first, then by days_over_sla descending
    items.sort(key=lambda x: (0 if x.severity == "critical" else 1, -x.days_over_sla))
    items = items[:15]

    critical_count = sum(1 for item in items if item.severity == "critical")

    return SLAAlertsSection(
        total=len(items),
        critical=critical_count,
        items=items,
    )


# =============================================================================
# ENDPOINT
# =============================================================================

@router.get("/today-summary", response_model=TodaySummaryResponse)
async def today_summary(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Aggregated LO "Today" dashboard summary.

    Returns appointments, tasks, leads needing follow-up, and SLA alerts
    in a single response, replacing 4 separate frontend calls.
    """
    current_user = await get_current_user(request, db)
    org_id = _get_org_id(current_user)
    models = get_models()

    if not models:
        raise HTTPException(status_code=503, detail="Scheduler models not available")

    now = datetime.now(timezone.utc)

    try:
        # Run all four queries using the shared sync session.
        # SQLAlchemy sync sessions are not thread-safe, so we execute
        # sequentially on the event loop thread (consistent with all other
        # scheduler endpoints). Each query is lightweight (indexed, bounded)
        # so total latency stays low.
        appointments = _fetch_today_appointments(db, models, current_user.id, org_id, now)
        tasks = _fetch_today_tasks(db, current_user.id, org_id, now)
        leads = _fetch_leads_needing_followup(db, current_user.id, org_id, now)
        sla_alerts = _fetch_sla_alerts(db, current_user.id, org_id, now)

        return TodaySummaryResponse(
            appointments=appointments,
            tasks=tasks,
            leads=leads,
            sla_alerts=sla_alerts,
            generated_at=now.isoformat(),
        )

    except Exception as e:
        logger.exception(f"Today summary failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate today summary")
