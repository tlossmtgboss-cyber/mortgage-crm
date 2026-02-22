"""
CRUD operations for SLA Tracking System.

Provides database operations for:
- SLA Measure configuration
- Milestone history tracking
- Performance snapshots
- Alerts management
"""

from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func, desc, text
from datetime import datetime, date, timedelta, timezone
from typing import Optional, List, Dict, Any, Tuple

from models.sla_tracking import (
    SLAMeasure,
    LoanMilestoneHistory,
    SLAPerformanceSnapshot,
    SLAAlert,
    SLAEfficiencyReport,
    TimeUnit,
    SLAStatus,
    MilestoneType,
    AlertStatus
)
from schemas.sla_tracking import (
    SLAMeasureCreate,
    SLAMeasureUpdate,
    MilestoneHistoryCreate,
    MilestoneHistoryUpdate,
    SLAAlertCreate,
    SLAAlertUpdate
)

import logging

logger = logging.getLogger(__name__)

# ============ Milestone Type to Loan Date Field Mapping ============
# Maps SLA milestone types to the corresponding loan date field
# This is used when completing an SLA task to update the loan's Important Dates

MILESTONE_TO_LOAN_DATE_FIELD = {
    # Appraisal milestones
    MilestoneType.APPRAISAL_ORDERED: "appraisal_ordered_date",
    MilestoneType.APPRAISAL_RECEIVED: "appraisal_completed_date",

    # Title milestones
    MilestoneType.TITLE_ORDERED: "title_ordered_date",
    MilestoneType.TITLE_RECEIVED: "title_received_date",

    # Insurance milestones
    MilestoneType.INSURANCE_ORDERED: "insurance_ordered_date",
    MilestoneType.INSURANCE_RECEIVED: "insurance_received_date",

    # Disclosure milestones
    MilestoneType.LE_PENDING: "loan_estimate_sent_date",
    MilestoneType.LE_DISCLOSED: "initial_disclosures_sent_date",

    # Underwriting milestones
    MilestoneType.SUBMITTED_TO_UW: "submitted_to_uw_date",
    MilestoneType.UW_DECISION: "uw_decision_date",
    MilestoneType.CONDITIONS_ISSUED: "conditional_approval_date",
    MilestoneType.CONDITIONS_CLEARED: "conditions_cleared_date",

    # Closing milestones
    MilestoneType.CLEAR_TO_CLOSE: "clear_to_close_date",
    MilestoneType.CLOSING_DOCS_OUT: "final_closing_package_sent_date",
    MilestoneType.CLOSING_SCHEDULED: "closing_date",
    MilestoneType.CLOSED: "closing_date",
    MilestoneType.FUNDED: "funded_date",

    # Lead/Pre-approval milestones
    MilestoneType.LEAD_RESPONSE: None,  # No date field - just activity
    MilestoneType.PRE_QUALIFIED: None,
    MilestoneType.PREAPPROVAL: None,
    MilestoneType.DOCUMENTS_REQUESTED: None,
    MilestoneType.DOCUMENTS_RECEIVED: None,
    MilestoneType.APPLICATION_COMPLETE: None,
    MilestoneType.APPLICATION_SUBMITTED: "contract_received_date",
    MilestoneType.DOCUMENT_COLLECTION: None,
    MilestoneType.PROCESSING_START: None,
}


# ============ SLA Measure CRUD ============

def create_sla_measure(
    db: Session,
    measure: SLAMeasureCreate,
    organization_id: int = 1
) -> SLAMeasure:
    """Create a new SLA measure configuration."""
    db_measure = SLAMeasure(
        organization_id=organization_id,
        milestone_type=measure.milestone_type,
        name=measure.name,
        description=measure.description,
        target_value=measure.target_value,
        target_unit=measure.target_unit,
        trigger_from=getattr(measure, 'trigger_from', 'previous_milestone') or 'previous_milestone',
        trigger_from_is_default=getattr(measure, 'trigger_from_is_default', False) or False,
        warning_threshold_pct=measure.warning_threshold_pct,
        critical_threshold_pct=measure.critical_threshold_pct,
        applies_to_loan_types=measure.applies_to_loan_types,
        applies_to_channels=measure.applies_to_channels,
        business_hours_only=measure.business_hours_only,
        is_active=measure.is_active
    )
    db.add(db_measure)
    db.commit()
    db.refresh(db_measure)
    return db_measure


def get_sla_measure(
    db: Session,
    measure_id: int,
    organization_id: int = 1
) -> Optional[SLAMeasure]:
    """Get a specific SLA measure by ID."""
    return db.query(SLAMeasure).filter(
        and_(
            SLAMeasure.id == measure_id,
            SLAMeasure.organization_id == organization_id
        )
    ).first()


def get_sla_measure_by_type(
    db: Session,
    milestone_type: MilestoneType,
    organization_id: int = 1
) -> Optional[SLAMeasure]:
    """Get SLA measure by milestone type.
    Falls back to org_id=1 (system defaults) if no measure found for the given org."""
    measure = db.query(SLAMeasure).filter(
        and_(
            SLAMeasure.milestone_type == milestone_type,
            SLAMeasure.organization_id == organization_id,
            SLAMeasure.is_active == True
        )
    ).first()

    # Fallback to system defaults (org 1) if no org-specific measure
    if not measure and organization_id != 1:
        measure = db.query(SLAMeasure).filter(
            and_(
                SLAMeasure.milestone_type == milestone_type,
                SLAMeasure.organization_id == 1,
                SLAMeasure.is_active == True
            )
        ).first()

    return measure


def get_all_sla_measures(
    db: Session,
    organization_id: int = 1,
    active_only: bool = True
) -> List[SLAMeasure]:
    """Get all SLA measures for an organization, ordered by display_order."""
    query = db.query(SLAMeasure).filter(
        SLAMeasure.organization_id == organization_id
    )
    if active_only:
        query = query.filter(SLAMeasure.is_active == True)
    return query.order_by(SLAMeasure.display_order, SLAMeasure.milestone_type).all()


def update_sla_measure(
    db: Session,
    measure_id: int,
    measure_update: SLAMeasureUpdate,
    organization_id: int = 1
) -> Optional[SLAMeasure]:
    """Update an SLA measure."""
    db_measure = get_sla_measure(db, measure_id, organization_id)
    if not db_measure:
        return None

    update_data = measure_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_measure, field, value)

    db.commit()
    db.refresh(db_measure)
    return db_measure


def delete_sla_measure(
    db: Session,
    measure_id: int,
    organization_id: int = 1
) -> bool:
    """Hard delete an SLA measure."""
    db_measure = get_sla_measure(db, measure_id, organization_id)
    if not db_measure:
        return False

    db.delete(db_measure)
    db.commit()
    return True


# ============ Milestone History CRUD ============

def create_milestone_history(
    db: Session,
    loan_id: Optional[int] = None,
    lead_id: Optional[int] = None,
    loan_number: Optional[str] = None,
    milestone_type: MilestoneType = None,
    assigned_to_id: Optional[int] = None,
    notes: Optional[str] = None,
    organization_id: int = 1
) -> Optional[LoanMilestoneHistory]:
    """Create a new milestone history record (start tracking a milestone)."""
    # Get the SLA measure for this milestone type
    sla_measure = get_sla_measure_by_type(db, milestone_type, organization_id)
    if not sla_measure:
        return None

    now = datetime.now(timezone.utc)

    # Calculate target deadline
    target_hours = calculate_target_hours(sla_measure)
    target_deadline = calculate_deadline(now, target_hours, sla_measure.business_hours_only)

    db_history = LoanMilestoneHistory(
        organization_id=organization_id,
        loan_id=loan_id,
        lead_id=lead_id,
        loan_number=loan_number,
        sla_measure_id=sla_measure.id,
        milestone_type=milestone_type,
        started_at=now,
        target_deadline=target_deadline,
        status=SLAStatus.IN_PROGRESS,
        target_hours=target_hours,
        assigned_to_id=assigned_to_id,
        notes=notes
    )
    db.add(db_history)
    db.commit()
    db.refresh(db_history)
    return db_history


def get_milestone_history(
    db: Session,
    history_id: int,
    organization_id: int = 1
) -> Optional[LoanMilestoneHistory]:
    """Get a specific milestone history record."""
    return db.query(LoanMilestoneHistory).filter(
        and_(
            LoanMilestoneHistory.id == history_id,
            LoanMilestoneHistory.organization_id == organization_id
        )
    ).first()


def get_loan_milestones(
    db: Session,
    loan_id: Optional[int] = None,
    lead_id: Optional[int] = None,
    organization_id: int = 1
) -> List[LoanMilestoneHistory]:
    """Get all milestones for a loan or lead."""
    query = db.query(LoanMilestoneHistory).filter(
        LoanMilestoneHistory.organization_id == organization_id
    )
    if loan_id:
        query = query.filter(LoanMilestoneHistory.loan_id == loan_id)
    elif lead_id:
        query = query.filter(LoanMilestoneHistory.lead_id == lead_id)
    else:
        return []

    return query.order_by(LoanMilestoneHistory.started_at).all()


def get_active_milestones(
    db: Session,
    organization_id: int = 1,
    status_filter: Optional[List[SLAStatus]] = None
) -> List[LoanMilestoneHistory]:
    """Get all active (in-progress) milestones."""
    query = db.query(LoanMilestoneHistory).filter(
        and_(
            LoanMilestoneHistory.organization_id == organization_id,
            LoanMilestoneHistory.status.in_([
                SLAStatus.IN_PROGRESS,
                SLAStatus.ON_TRACK,
                SLAStatus.AT_RISK,
                SLAStatus.OVERDUE
            ])
        )
    )
    if status_filter:
        query = query.filter(LoanMilestoneHistory.status.in_(status_filter))

    return query.order_by(LoanMilestoneHistory.target_deadline).all()


def get_overdue_milestones(
    db: Session,
    organization_id: int = 1
) -> List[LoanMilestoneHistory]:
    """Get all overdue milestones."""
    return db.query(LoanMilestoneHistory).filter(
        and_(
            LoanMilestoneHistory.organization_id == organization_id,
            LoanMilestoneHistory.status == SLAStatus.OVERDUE
        )
    ).order_by(LoanMilestoneHistory.target_deadline).all()


def get_at_risk_milestones(
    db: Session,
    organization_id: int = 1
) -> List[LoanMilestoneHistory]:
    """Get all at-risk milestones."""
    return db.query(LoanMilestoneHistory).filter(
        and_(
            LoanMilestoneHistory.organization_id == organization_id,
            LoanMilestoneHistory.status == SLAStatus.AT_RISK
        )
    ).order_by(LoanMilestoneHistory.target_deadline).all()


def complete_milestone(
    db: Session,
    history_id: int,
    completed_by_id: Optional[int] = None,
    notes: Optional[str] = None,
    organization_id: int = 1
) -> Optional[LoanMilestoneHistory]:
    """Mark a milestone as completed and calculate performance metrics."""
    db_history = get_milestone_history(db, history_id, organization_id)
    if not db_history or db_history.status == SLAStatus.COMPLETED:
        return None

    now = datetime.now(timezone.utc)
    db_history.completed_at = now
    db_history.completed_by_id = completed_by_id
    db_history.status = SLAStatus.COMPLETED

    if notes:
        db_history.notes = (db_history.notes or "") + f"\n[Completed]: {notes}"

    # Calculate actual time and variance
    if db_history.started_at:
        actual_hours = (now - db_history.started_at).total_seconds() / 3600
        db_history.actual_hours = actual_hours

        if db_history.target_hours:
            variance = actual_hours - db_history.target_hours
            db_history.variance_hours = variance
            db_history.variance_pct = (variance / db_history.target_hours) * 100

    db.commit()
    db.refresh(db_history)
    return db_history


def waive_milestone(
    db: Session,
    history_id: int,
    waive_reason: str,
    organization_id: int = 1
) -> Optional[LoanMilestoneHistory]:
    """Waive a milestone (e.g., external dependencies)."""
    db_history = get_milestone_history(db, history_id, organization_id)
    if not db_history:
        return None

    db_history.status = SLAStatus.WAIVED
    db_history.waive_reason = waive_reason
    db_history.completed_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(db_history)
    return db_history


def update_milestone_status(
    db: Session,
    history_id: int,
    new_status: SLAStatus,
    organization_id: int = 1
) -> Optional[LoanMilestoneHistory]:
    """Update milestone status (used by background jobs)."""
    db_history = get_milestone_history(db, history_id, organization_id)
    if not db_history:
        return None

    db_history.status = new_status
    db.commit()
    db.refresh(db_history)
    return db_history


def create_sla_warning_task(
    db: Session,
    milestone: LoanMilestoneHistory,
    sla_measure: SLAMeasure
) -> Optional[int]:
    """
    Create a task for a milestone that has hit warning status.
    The task allows the user to enter the milestone date which will update Important Dates.

    Returns the task ID if created, None if task already exists or creation failed.
    """
    # Import Task model here to avoid circular imports
    from database.models import Task

    try:
        # Check if task already exists for this milestone
        existing_task = db.query(Task).filter(
            Task.sla_milestone_id == milestone.id,
            Task.status != "completed"
        ).first()

        if existing_task:
            logger.debug(f"SLA task already exists for milestone {milestone.id}")
            return None

        # Skip SLA warning if an active workflow already has pending tasks for this entity
        # The workflow IS the action plan for hitting milestones
        if milestone.lead_id:
            entity_filter = "wti.lead_id = :entity_id"
            entity_id = milestone.lead_id
        elif milestone.loan_id:
            entity_filter = "wti.loan_id = :entity_id"
            entity_id = milestone.loan_id
        else:
            entity_id = None

        if entity_id:
            active_workflow_tasks = db.execute(text(f"""
                SELECT COUNT(*) FROM workflow_task_instances wti
                JOIN workflow_instances wi ON wi.id = wti.workflow_instance_id
                WHERE {entity_filter}
                AND wti.status IN ('scheduled', 'pending', 'in_progress')
                AND wi.status = 'active'
            """), {"entity_id": entity_id}).scalar()

            if active_workflow_tasks and active_workflow_tasks > 0:
                logger.info(
                    f"Skipping SLA warning task for milestone {milestone.id} — "
                    f"{active_workflow_tasks} active workflow tasks already exist"
                )
                return None

        # Get the loan date field for this milestone type
        date_field = MILESTONE_TO_LOAN_DATE_FIELD.get(milestone.milestone_type)

        # Format milestone type for display
        milestone_name = milestone.milestone_type.value.replace("_", " ").title()

        # Create task title and description
        task_title = f"⚠️ SLA Warning: {milestone_name}"
        task_description = (
            f"This milestone is approaching its SLA deadline.\n\n"
            f"Target: {sla_measure.target_value} {sla_measure.target_unit.value}\n"
            f"Deadline: {milestone.target_deadline.strftime('%Y-%m-%d %H:%M') if milestone.target_deadline else 'Not set'}\n\n"
            f"When you complete this milestone, enter the date it was completed to update the loan's Important Dates."
        )

        # Create the task
        new_task = Task(
            title=task_title,
            description=task_description,
            status="pending",
            priority="high",
            due_date=milestone.target_deadline,
            owner_id=milestone.assigned_to_id,
            lead_id=milestone.lead_id,
            loan_id=milestone.loan_id,
            related_contact_name=milestone.loan_number,
            related_type="sla_milestone",
            # SLA tracking fields
            sla_milestone_id=milestone.id,
            sla_milestone_type=milestone.milestone_type.value,
            sla_date_field=date_field
        )

        db.add(new_task)
        db.flush()  # Get the task ID without committing

        logger.info(f"Created SLA warning task {new_task.id} for milestone {milestone.id} ({milestone_name})")
        return new_task.id

    except Exception as e:
        logger.error(f"Error creating SLA warning task for milestone {milestone.id}: {e}")
        return None


def update_milestone_statuses_batch(
    db: Session,
    organization_id: int = 1
) -> Dict[str, int]:
    """
    Batch update all milestone statuses based on current time.
    Called periodically by background job.
    Also creates tasks for milestones that hit warning status.
    """
    now = datetime.now(timezone.utc)
    updated_counts = {"at_risk": 0, "overdue": 0, "tasks_created": 0}

    # Get all active milestones
    active = db.query(LoanMilestoneHistory).filter(
        and_(
            LoanMilestoneHistory.organization_id == organization_id,
            LoanMilestoneHistory.status.in_([
                SLAStatus.IN_PROGRESS,
                SLAStatus.ON_TRACK,
                SLAStatus.AT_RISK
            ]),
            LoanMilestoneHistory.target_deadline.isnot(None)
        )
    ).all()

    for milestone in active:
        # Get warning threshold from SLA measure
        sla_measure = db.query(SLAMeasure).filter(
            SLAMeasure.id == milestone.sla_measure_id
        ).first()

        if not sla_measure:
            continue

        # Check if overdue
        if now > milestone.target_deadline:
            if milestone.status != SLAStatus.OVERDUE:
                milestone.status = SLAStatus.OVERDUE
                updated_counts["overdue"] += 1
                # Create task for overdue milestone if not already created
                task_id = create_sla_warning_task(db, milestone, sla_measure)
                if task_id:
                    updated_counts["tasks_created"] += 1
        else:
            # Check if at risk (past warning threshold)
            warning_time = milestone.started_at + timedelta(
                hours=milestone.target_hours * (sla_measure.warning_threshold_pct / 100)
            )
            if now > warning_time and milestone.status not in [SLAStatus.AT_RISK, SLAStatus.OVERDUE]:
                milestone.status = SLAStatus.AT_RISK
                updated_counts["at_risk"] += 1
                # Create task for at-risk milestone
                task_id = create_sla_warning_task(db, milestone, sla_measure)
                if task_id:
                    updated_counts["tasks_created"] += 1
            elif now <= warning_time and milestone.status not in [SLAStatus.IN_PROGRESS, SLAStatus.ON_TRACK]:
                milestone.status = SLAStatus.ON_TRACK

    db.commit()
    return updated_counts


# ============ SLA Alert CRUD ============

def create_sla_alert(
    db: Session,
    alert: SLAAlertCreate,
    organization_id: int = 1
) -> SLAAlert:
    """Create a new SLA alert."""
    db_alert = SLAAlert(
        organization_id=organization_id,
        milestone_history_id=alert.milestone_history_id,
        loan_id=alert.loan_id,
        lead_id=alert.lead_id,
        alert_type=alert.alert_type,
        milestone_type=alert.milestone_type,
        title=alert.title,
        message=alert.message,
        status=AlertStatus.ACTIVE,
        assigned_to_id=alert.assigned_to_id
    )
    db.add(db_alert)
    db.commit()
    db.refresh(db_alert)
    return db_alert


def get_sla_alert(
    db: Session,
    alert_id: int,
    organization_id: int = 1
) -> Optional[SLAAlert]:
    """Get a specific SLA alert."""
    return db.query(SLAAlert).filter(
        and_(
            SLAAlert.id == alert_id,
            SLAAlert.organization_id == organization_id
        )
    ).first()


def get_active_alerts(
    db: Session,
    organization_id: int = 1,
    limit: int = 50
) -> List[SLAAlert]:
    """Get all active alerts."""
    return db.query(SLAAlert).filter(
        and_(
            SLAAlert.organization_id == organization_id,
            SLAAlert.status == AlertStatus.ACTIVE
        )
    ).order_by(desc(SLAAlert.triggered_at)).limit(limit).all()


def get_alerts_for_loan(
    db: Session,
    loan_id: Optional[int] = None,
    lead_id: Optional[int] = None,
    organization_id: int = 1
) -> List[SLAAlert]:
    """Get all alerts for a specific loan or lead."""
    query = db.query(SLAAlert).filter(
        SLAAlert.organization_id == organization_id
    )
    if loan_id:
        query = query.filter(SLAAlert.loan_id == loan_id)
    elif lead_id:
        query = query.filter(SLAAlert.lead_id == lead_id)
    else:
        return []

    return query.order_by(desc(SLAAlert.triggered_at)).all()


def acknowledge_alert(
    db: Session,
    alert_id: int,
    notes: Optional[str] = None,
    organization_id: int = 1
) -> Optional[SLAAlert]:
    """Acknowledge an alert."""
    db_alert = get_sla_alert(db, alert_id, organization_id)
    if not db_alert:
        return None

    db_alert.status = AlertStatus.ACKNOWLEDGED
    db_alert.acknowledged_at = datetime.now(timezone.utc)
    if notes:
        db_alert.resolution_notes = notes

    db.commit()
    db.refresh(db_alert)
    return db_alert


def resolve_alert(
    db: Session,
    alert_id: int,
    resolution_notes: str,
    organization_id: int = 1
) -> Optional[SLAAlert]:
    """Resolve an alert."""
    db_alert = get_sla_alert(db, alert_id, organization_id)
    if not db_alert:
        return None

    db_alert.status = AlertStatus.RESOLVED
    db_alert.resolved_at = datetime.now(timezone.utc)
    db_alert.resolution_notes = resolution_notes

    db.commit()
    db.refresh(db_alert)
    return db_alert


def escalate_alert(
    db: Session,
    alert_id: int,
    escalated_to_id: int,
    notes: Optional[str] = None,
    organization_id: int = 1
) -> Optional[SLAAlert]:
    """Escalate an alert to a higher authority."""
    db_alert = get_sla_alert(db, alert_id, organization_id)
    if not db_alert:
        return None

    db_alert.status = AlertStatus.ESCALATED
    db_alert.escalated_to_id = escalated_to_id
    if notes:
        db_alert.resolution_notes = (db_alert.resolution_notes or "") + f"\n[Escalated]: {notes}"

    db.commit()
    db.refresh(db_alert)
    return db_alert


def snooze_alert(
    db: Session,
    alert_id: int,
    snooze_until: datetime,
    notes: Optional[str] = None,
    organization_id: int = 1
) -> Optional[SLAAlert]:
    """Snooze an alert until a specified time."""
    db_alert = get_sla_alert(db, alert_id, organization_id)
    if not db_alert:
        return None

    db_alert.status = AlertStatus.SNOOZED
    db_alert.snooze_until = snooze_until
    if notes:
        db_alert.resolution_notes = (db_alert.resolution_notes or "") + f"\n[Snoozed]: {notes}"

    db.commit()
    db.refresh(db_alert)
    return db_alert


def reactivate_snoozed_alerts(
    db: Session,
    organization_id: int = 1
) -> int:
    """Reactivate snoozed alerts that have passed their snooze time."""
    now = datetime.now(timezone.utc)

    updated = db.query(SLAAlert).filter(
        and_(
            SLAAlert.organization_id == organization_id,
            SLAAlert.status == AlertStatus.SNOOZED,
            SLAAlert.snooze_until <= now
        )
    ).update({"status": AlertStatus.ACTIVE})

    db.commit()
    return updated


# ============ Performance Snapshot CRUD ============

def create_performance_snapshot(
    db: Session,
    snapshot_date: date,
    scope_type: str,
    scope_id: Optional[int] = None,
    milestone_type: Optional[MilestoneType] = None,
    period_type: str = "daily",
    organization_id: int = 1
) -> SLAPerformanceSnapshot:
    """Create a performance snapshot (called by background job)."""
    # Calculate metrics
    metrics = calculate_snapshot_metrics(
        db, snapshot_date, scope_type, scope_id, milestone_type, organization_id
    )

    db_snapshot = SLAPerformanceSnapshot(
        organization_id=organization_id,
        snapshot_date=snapshot_date,
        period_type=period_type,
        scope_type=scope_type,
        scope_id=scope_id,
        milestone_type=milestone_type,
        **metrics
    )
    db.add(db_snapshot)
    db.commit()
    db.refresh(db_snapshot)
    return db_snapshot


def get_performance_snapshots(
    db: Session,
    start_date: date,
    end_date: date,
    scope_type: str = "organization",
    scope_id: Optional[int] = None,
    milestone_type: Optional[MilestoneType] = None,
    organization_id: int = 1
) -> List[SLAPerformanceSnapshot]:
    """Get performance snapshots for a date range."""
    query = db.query(SLAPerformanceSnapshot).filter(
        and_(
            SLAPerformanceSnapshot.organization_id == organization_id,
            SLAPerformanceSnapshot.snapshot_date >= start_date,
            SLAPerformanceSnapshot.snapshot_date <= end_date,
            SLAPerformanceSnapshot.scope_type == scope_type
        )
    )
    if scope_id:
        query = query.filter(SLAPerformanceSnapshot.scope_id == scope_id)
    if milestone_type:
        query = query.filter(SLAPerformanceSnapshot.milestone_type == milestone_type)

    return query.order_by(SLAPerformanceSnapshot.snapshot_date).all()


# ============ Efficiency Report CRUD ============

def create_efficiency_report(
    db: Session,
    period_start: date,
    period_end: date,
    organization_id: int = 1
) -> SLAEfficiencyReport:
    """Generate an efficiency report for a period."""
    # Calculate comprehensive metrics
    metrics = calculate_efficiency_metrics(db, period_start, period_end, organization_id)

    db_report = SLAEfficiencyReport(
        organization_id=organization_id,
        report_date=date.today(),
        period_start=period_start,
        period_end=period_end,
        **metrics
    )
    db.add(db_report)
    db.commit()
    db.refresh(db_report)
    return db_report


def get_efficiency_reports(
    db: Session,
    organization_id: int = 1,
    limit: int = 10
) -> List[SLAEfficiencyReport]:
    """Get recent efficiency reports."""
    return db.query(SLAEfficiencyReport).filter(
        SLAEfficiencyReport.organization_id == organization_id
    ).order_by(desc(SLAEfficiencyReport.report_date)).limit(limit).all()


# ============ Dashboard Queries ============

def get_dashboard_summary(
    db: Session,
    organization_id: int = 1
) -> Dict[str, Any]:
    """Get summary metrics for the SLA dashboard."""
    active_milestones = get_active_milestones(db, organization_id)

    on_track = len([m for m in active_milestones if m.status in [SLAStatus.IN_PROGRESS, SLAStatus.ON_TRACK]])
    at_risk = len([m for m in active_milestones if m.status == SLAStatus.AT_RISK])
    overdue = len([m for m in active_milestones if m.status == SLAStatus.OVERDUE])

    # Calculate on-time rate from recent completions
    recent_completed = db.query(LoanMilestoneHistory).filter(
        and_(
            LoanMilestoneHistory.organization_id == organization_id,
            LoanMilestoneHistory.status == SLAStatus.COMPLETED,
            LoanMilestoneHistory.completed_at >= datetime.now(timezone.utc) - timedelta(days=30)
        )
    ).all()

    on_time_count = len([m for m in recent_completed if m.variance_hours and m.variance_hours <= 0])
    on_time_rate = (on_time_count / len(recent_completed) * 100) if recent_completed else 0

    avg_completion = sum(m.actual_hours or 0 for m in recent_completed) / len(recent_completed) if recent_completed else 0

    active_alerts = db.query(SLAAlert).filter(
        and_(
            SLAAlert.organization_id == organization_id,
            SLAAlert.status == AlertStatus.ACTIVE
        )
    ).count()

    # Milestone breakdown by type
    milestone_breakdown = {}
    for milestone in active_milestones:
        mt = milestone.milestone_type.value if milestone.milestone_type else "unknown"
        if mt not in milestone_breakdown:
            milestone_breakdown[mt] = {"total": 0, "on_track": 0, "at_risk": 0, "overdue": 0}
        milestone_breakdown[mt]["total"] += 1
        if milestone.status in [SLAStatus.IN_PROGRESS, SLAStatus.ON_TRACK]:
            milestone_breakdown[mt]["on_track"] += 1
        elif milestone.status == SLAStatus.AT_RISK:
            milestone_breakdown[mt]["at_risk"] += 1
        elif milestone.status == SLAStatus.OVERDUE:
            milestone_breakdown[mt]["overdue"] += 1

    return {
        "total_active_milestones": len(active_milestones),
        "on_track_count": on_track,
        "at_risk_count": at_risk,
        "overdue_count": overdue,
        "overall_on_time_rate": round(on_time_rate, 1),
        "avg_completion_time_hours": round(avg_completion, 1),
        "active_alerts_count": active_alerts,
        "milestone_breakdown": milestone_breakdown
    }


def get_team_performance(
    db: Session,
    start_date: date,
    end_date: date,
    team_id: Optional[int] = None,
    organization_id: int = 1
) -> List[Dict[str, Any]]:
    """Get performance metrics grouped by team member."""
    # This would join with users table to get team member info
    # Simplified version for now
    results = db.query(
        LoanMilestoneHistory.assigned_to_id,
        func.count(LoanMilestoneHistory.id).label('total'),
        func.sum(
            func.case(
                (LoanMilestoneHistory.variance_hours <= 0, 1),
                else_=0
            )
        ).label('on_time'),
        func.avg(LoanMilestoneHistory.actual_hours).label('avg_hours')
    ).filter(
        and_(
            LoanMilestoneHistory.organization_id == organization_id,
            LoanMilestoneHistory.status == SLAStatus.COMPLETED,
            LoanMilestoneHistory.completed_at >= datetime.combine(start_date, datetime.min.time()),
            LoanMilestoneHistory.completed_at <= datetime.combine(end_date, datetime.max.time())
        )
    ).group_by(LoanMilestoneHistory.assigned_to_id).all()

    team_performance = []
    for row in results:
        if row.assigned_to_id:
            on_time_rate = (row.on_time / row.total * 100) if row.total > 0 else 0
            team_performance.append({
                "user_id": row.assigned_to_id,
                "total_milestones": row.total,
                "completed_on_time": row.on_time or 0,
                "on_time_rate": round(on_time_rate, 1),
                "avg_completion_hours": round(row.avg_hours or 0, 1)
            })

    return team_performance


def get_bottleneck_analysis(
    db: Session,
    start_date: date,
    end_date: date,
    organization_id: int = 1
) -> List[Dict[str, Any]]:
    """Identify bottleneck stages based on delays."""
    results = db.query(
        LoanMilestoneHistory.milestone_type,
        func.avg(LoanMilestoneHistory.variance_hours).label('avg_variance'),
        func.count(
            func.case(
                (LoanMilestoneHistory.variance_hours > 0, 1),
                else_=None
            )
        ).label('delayed_count'),
        func.count(LoanMilestoneHistory.id).label('total_count')
    ).filter(
        and_(
            LoanMilestoneHistory.organization_id == organization_id,
            LoanMilestoneHistory.status == SLAStatus.COMPLETED,
            LoanMilestoneHistory.completed_at >= datetime.combine(start_date, datetime.min.time()),
            LoanMilestoneHistory.completed_at <= datetime.combine(end_date, datetime.max.time())
        )
    ).group_by(LoanMilestoneHistory.milestone_type).all()

    bottlenecks = []
    for row in results:
        if row.avg_variance and row.avg_variance > 0:
            delay_rate = (row.delayed_count / row.total_count * 100) if row.total_count > 0 else 0
            bottlenecks.append({
                "milestone_type": row.milestone_type.value if row.milestone_type else "unknown",
                "avg_delay_hours": round(row.avg_variance, 1),
                "delay_frequency_pct": round(delay_rate, 1),
                "total_affected_loans": row.delayed_count
            })

    # Sort by avg delay descending
    bottlenecks.sort(key=lambda x: x["avg_delay_hours"], reverse=True)
    return bottlenecks


# ============ Helper Functions ============

def calculate_target_hours(sla_measure: SLAMeasure) -> float:
    """Convert target value to hours."""
    if sla_measure.target_unit == TimeUnit.HOURS:
        return sla_measure.target_value
    elif sla_measure.target_unit == TimeUnit.DAYS:
        return sla_measure.target_value * 24
    elif sla_measure.target_unit == TimeUnit.BUSINESS_DAYS:
        return sla_measure.target_value * 8  # Assuming 8-hour business day
    return sla_measure.target_value


def is_business_hour(dt: datetime) -> bool:
    """Check if a datetime falls within business hours (9 AM - 5 PM, Mon-Fri)."""
    # Check if it's a weekday (Monday = 0, Sunday = 6)
    if dt.weekday() >= 5:  # Saturday or Sunday
        return False
    # Check if it's within business hours (9 AM to 5 PM)
    return 9 <= dt.hour < 17


def get_next_business_hour(dt: datetime) -> datetime:
    """Get the next business hour start from a given datetime."""
    # If it's a weekend, move to Monday 9 AM
    while dt.weekday() >= 5:
        dt = dt + timedelta(days=1)
        dt = dt.replace(hour=9, minute=0, second=0, microsecond=0)

    # If before business hours, move to 9 AM same day
    if dt.hour < 9:
        return dt.replace(hour=9, minute=0, second=0, microsecond=0)

    # If after business hours, move to 9 AM next business day
    if dt.hour >= 17:
        dt = dt + timedelta(days=1)
        dt = dt.replace(hour=9, minute=0, second=0, microsecond=0)
        # Skip weekends
        while dt.weekday() >= 5:
            dt = dt + timedelta(days=1)
        return dt

    # Already in business hours
    return dt


def calculate_deadline(
    start_time: datetime,
    target_hours: float,
    business_hours_only: bool = False
) -> datetime:
    """Calculate the deadline based on start time and target hours.

    Args:
        start_time: When the SLA clock starts
        target_hours: Number of hours until deadline
        business_hours_only: If True, only count business hours (9 AM - 5 PM, Mon-Fri)

    Returns:
        The calculated deadline datetime
    """
    if not business_hours_only:
        return start_time + timedelta(hours=target_hours)

    # Business hours calculation
    # Business hours: 9 AM - 5 PM (8 hours per day)
    # Business days: Monday - Friday

    remaining_hours = target_hours
    current_time = get_next_business_hour(start_time)

    while remaining_hours > 0:
        # Calculate hours remaining in current business day
        end_of_day = current_time.replace(hour=17, minute=0, second=0, microsecond=0)
        hours_left_today = (end_of_day - current_time).total_seconds() / 3600

        if hours_left_today <= 0:
            # Move to next business day
            current_time = current_time + timedelta(days=1)
            current_time = current_time.replace(hour=9, minute=0, second=0, microsecond=0)
            # Skip weekends
            while current_time.weekday() >= 5:
                current_time = current_time + timedelta(days=1)
            continue

        if remaining_hours <= hours_left_today:
            # Deadline is within today's business hours
            current_time = current_time + timedelta(hours=remaining_hours)
            remaining_hours = 0
        else:
            # Use up today's remaining hours and move to next business day
            remaining_hours -= hours_left_today
            current_time = current_time + timedelta(days=1)
            current_time = current_time.replace(hour=9, minute=0, second=0, microsecond=0)
            # Skip weekends
            while current_time.weekday() >= 5:
                current_time = current_time + timedelta(days=1)

    return current_time


def calculate_snapshot_metrics(
    db: Session,
    snapshot_date: date,
    scope_type: str,
    scope_id: Optional[int],
    milestone_type: Optional[MilestoneType],
    organization_id: int
) -> Dict[str, Any]:
    """Calculate metrics for a performance snapshot."""
    # Build base query
    query = db.query(LoanMilestoneHistory).filter(
        and_(
            LoanMilestoneHistory.organization_id == organization_id,
            func.date(LoanMilestoneHistory.completed_at) == snapshot_date
        )
    )

    if scope_type == "user" and scope_id:
        query = query.filter(LoanMilestoneHistory.assigned_to_id == scope_id)
    if milestone_type:
        query = query.filter(LoanMilestoneHistory.milestone_type == milestone_type)

    milestones = query.all()

    completed_on_time = len([m for m in milestones if m.variance_hours and m.variance_hours <= 0])
    completed_late = len([m for m in milestones if m.variance_hours and m.variance_hours > 0])

    # Get in-progress counts
    in_progress = db.query(LoanMilestoneHistory).filter(
        and_(
            LoanMilestoneHistory.organization_id == organization_id,
            LoanMilestoneHistory.status.in_([SLAStatus.IN_PROGRESS, SLAStatus.ON_TRACK, SLAStatus.AT_RISK])
        )
    ).count()

    overdue = db.query(LoanMilestoneHistory).filter(
        and_(
            LoanMilestoneHistory.organization_id == organization_id,
            LoanMilestoneHistory.status == SLAStatus.OVERDUE
        )
    ).count()

    total = completed_on_time + completed_late
    on_time_rate = (completed_on_time / total * 100) if total > 0 else 0
    avg_completion = sum(m.actual_hours or 0 for m in milestones) / len(milestones) if milestones else 0
    avg_variance = sum(m.variance_hours or 0 for m in milestones) / len(milestones) if milestones else 0

    return {
        "total_milestones": total,
        "completed_on_time": completed_on_time,
        "completed_late": completed_late,
        "still_in_progress": in_progress,
        "overdue": overdue,
        "on_time_rate": round(on_time_rate, 1),
        "avg_completion_time_hours": round(avg_completion, 1),
        "avg_variance_hours": round(avg_variance, 1),
        "avg_variance_pct": round((avg_variance / avg_completion * 100), 1) if avg_completion > 0 else 0
    }


def calculate_efficiency_metrics(
    db: Session,
    period_start: date,
    period_end: date,
    organization_id: int
) -> Dict[str, Any]:
    """Calculate comprehensive efficiency metrics for a report."""
    # Get completed milestones in period
    completed = db.query(LoanMilestoneHistory).filter(
        and_(
            LoanMilestoneHistory.organization_id == organization_id,
            LoanMilestoneHistory.status == SLAStatus.COMPLETED,
            func.date(LoanMilestoneHistory.completed_at) >= period_start,
            func.date(LoanMilestoneHistory.completed_at) <= period_end
        )
    ).all()

    # Calculate overall metrics
    total_loans = len(set(m.loan_id for m in completed if m.loan_id))
    on_time = len([m for m in completed if m.variance_hours and m.variance_hours <= 0])
    compliance_rate = (on_time / len(completed) * 100) if completed else 0

    # Bottleneck analysis
    bottlenecks = get_bottleneck_analysis(db, period_start, period_end, organization_id)

    # Team performance for top performers
    team_perf = get_team_performance(db, period_start, period_end, None, organization_id)
    top_performers = sorted(team_perf, key=lambda x: x["on_time_rate"], reverse=True)[:5]

    # Improvement areas (milestones with worst performance)
    improvement_areas = [b for b in bottlenecks if b["delay_frequency_pct"] > 20]

    return {
        "total_loans_processed": total_loans,
        "overall_sla_compliance_rate": round(compliance_rate, 1),
        "bottleneck_stages": bottlenecks[:5],  # Top 5 bottlenecks
        "top_performers": top_performers,
        "improvement_areas": improvement_areas,
        "recommendations": generate_recommendations(bottlenecks, compliance_rate)
    }


def generate_recommendations(
    bottlenecks: List[Dict[str, Any]],
    compliance_rate: float
) -> List[str]:
    """Generate improvement recommendations based on analysis."""
    recommendations = []

    if compliance_rate < 80:
        recommendations.append("Overall SLA compliance is below 80%. Consider reviewing staffing levels and process efficiency.")

    for bottleneck in bottlenecks[:3]:
        if bottleneck["delay_frequency_pct"] > 30:
            recommendations.append(
                f"High delay frequency ({bottleneck['delay_frequency_pct']}%) at {bottleneck['milestone_type']} stage. "
                f"Review process and consider additional resources."
            )

    if not recommendations:
        recommendations.append("Performance is within acceptable parameters. Continue monitoring for trends.")

    return recommendations


# ============ Seed Default SLA Measures ============

def seed_default_sla_measures(
    db: Session,
    organization_id: int = 1
) -> List[SLAMeasure]:
    """Seed default SLA measures for a new organization."""
    default_measures = [
        # Lead Stage
        {"milestone_type": MilestoneType.LEAD_RESPONSE, "name": "Lead Response Time", "target_value": 4, "target_unit": TimeUnit.HOURS, "description": "Time to first contact with new lead"},
        {"milestone_type": MilestoneType.PRE_QUALIFIED, "name": "Pre-Qualification", "target_value": 24, "target_unit": TimeUnit.HOURS, "description": "Qualify the lead"},
        {"milestone_type": MilestoneType.PREAPPROVAL, "name": "Pre-Approval Issuance", "target_value": 2, "target_unit": TimeUnit.BUSINESS_DAYS, "description": "Issue pre-approval letter"},

        # Application Stage
        {"milestone_type": MilestoneType.APPLICATION_SUBMITTED, "name": "Application Submission", "target_value": 3, "target_unit": TimeUnit.BUSINESS_DAYS, "description": "Full application submitted"},
        {"milestone_type": MilestoneType.DOCUMENT_COLLECTION, "name": "Document Collection", "target_value": 5, "target_unit": TimeUnit.BUSINESS_DAYS, "description": "Collect all required documents"},
        {"milestone_type": MilestoneType.APPLICATION_COMPLETE, "name": "Application Complete", "target_value": 7, "target_unit": TimeUnit.BUSINESS_DAYS, "description": "Application package complete"},

        # Processing Stage
        {"milestone_type": MilestoneType.APPRAISAL_ORDERED, "name": "Appraisal Ordered", "target_value": 1, "target_unit": TimeUnit.BUSINESS_DAYS, "description": "Order appraisal"},
        {"milestone_type": MilestoneType.APPRAISAL_RECEIVED, "name": "Appraisal Received", "target_value": 7, "target_unit": TimeUnit.BUSINESS_DAYS, "description": "Receive completed appraisal"},
        {"milestone_type": MilestoneType.TITLE_ORDERED, "name": "Title Ordered", "target_value": 1, "target_unit": TimeUnit.BUSINESS_DAYS, "description": "Order title search"},
        {"milestone_type": MilestoneType.TITLE_RECEIVED, "name": "Title Received", "target_value": 5, "target_unit": TimeUnit.BUSINESS_DAYS, "description": "Receive title commitment"},

        # Underwriting Stage
        {"milestone_type": MilestoneType.SUBMITTED_TO_UW, "name": "Submit to Underwriting", "target_value": 2, "target_unit": TimeUnit.BUSINESS_DAYS, "description": "Submit to underwriting"},
        {"milestone_type": MilestoneType.UW_DECISION, "name": "Underwriting Decision", "target_value": 3, "target_unit": TimeUnit.BUSINESS_DAYS, "description": "Receive underwriting decision"},
        {"milestone_type": MilestoneType.CONDITIONS_CLEARED, "name": "Conditions Cleared", "target_value": 3, "target_unit": TimeUnit.BUSINESS_DAYS, "description": "Clear all conditions"},

        # Closing Stage
        {"milestone_type": MilestoneType.CLEAR_TO_CLOSE, "name": "Clear to Close", "target_value": 2, "target_unit": TimeUnit.BUSINESS_DAYS, "description": "Receive CTC"},
        {"milestone_type": MilestoneType.CLOSING_DOCS_OUT, "name": "Closing Docs Out", "target_value": 1, "target_unit": TimeUnit.BUSINESS_DAYS, "description": "Send closing docs"},
        {"milestone_type": MilestoneType.FUNDED, "name": "Loan Funded", "target_value": 1, "target_unit": TimeUnit.BUSINESS_DAYS, "description": "Fund the loan"}
    ]

    created_measures = []
    for measure_data in default_measures:
        # Check if measure already exists
        existing = db.query(SLAMeasure).filter(
            and_(
                SLAMeasure.organization_id == organization_id,
                SLAMeasure.milestone_type == measure_data["milestone_type"]
            )
        ).first()

        if not existing:
            measure = SLAMeasure(
                organization_id=organization_id,
                **measure_data
            )
            db.add(measure)
            created_measures.append(measure)

    if created_measures:
        db.commit()
        for m in created_measures:
            db.refresh(m)

    return created_measures


# ============ SLA Task Completion ============

def complete_sla_task_with_date(
    db: Session,
    task_id: int,
    milestone_date: datetime,
    user_id: int,
    organization_id: int = 1
) -> Dict[str, Any]:
    """
    Complete an SLA warning task with the milestone date.
    Updates the loan's Important Dates field and completes the SLA milestone.

    Args:
        db: Database session
        task_id: ID of the task to complete
        milestone_date: The date the milestone was actually completed
        user_id: ID of the user completing the task
        organization_id: Organization ID

    Returns:
        Dict with result details including loan_updated, milestone_completed status
    """
    # Import Task and Loan models here to avoid circular imports
    from database.models import Task, Loan

    result = {
        "success": False,
        "task_id": task_id,
        "task_completed": False,
        "loan_updated": False,
        "milestone_completed": False,
        "loan_field_updated": None,
        "error": None
    }

    try:
        # Get the task
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            result["error"] = "Task not found"
            return result

        # Verify it's an SLA task
        if not task.sla_milestone_id:
            result["error"] = "This is not an SLA milestone task"
            return result

        # Store the milestone date on the task
        task.milestone_date = milestone_date
        task.status = "completed"
        task.completed_at = datetime.now(timezone.utc)

        result["task_completed"] = True

        # Update the loan's Important Dates if there's a date field mapping
        if task.sla_date_field and task.loan_id:
            loan = db.query(Loan).filter(Loan.id == task.loan_id).first()
            if loan and hasattr(loan, task.sla_date_field):
                setattr(loan, task.sla_date_field, milestone_date)
                loan.updated_at = datetime.now(timezone.utc)
                result["loan_updated"] = True
                result["loan_field_updated"] = task.sla_date_field
                logger.info(f"Updated loan {loan.id} field {task.sla_date_field} to {milestone_date}")

        # Complete the SLA milestone
        if task.sla_milestone_id:
            milestone = get_milestone_history(db, task.sla_milestone_id, organization_id)
            if milestone:
                completed_milestone = complete_milestone(
                    db,
                    task.sla_milestone_id,
                    completed_by_id=user_id,
                    notes=f"Completed via task. Milestone date: {milestone_date.strftime('%Y-%m-%d')}",
                    organization_id=organization_id
                )
                if completed_milestone:
                    result["milestone_completed"] = True
                    logger.info(f"Completed SLA milestone {task.sla_milestone_id}")

        # Cancel pending workflow tasks for same entity — milestone was completed via SLA path
        entity_id = task.loan_id or task.lead_id
        entity_col = "loan_id" if task.loan_id else "lead_id"
        if entity_id:
            wf_cancelled = db.execute(text(f"""
                UPDATE tasks
                SET status = 'cancelled', updated_at = NOW()
                WHERE {entity_col} = :entity_id
                AND workflow_task_instance_id IS NOT NULL
                AND status IN ('pending')
                AND sla_milestone_id IS NULL
            """), {"entity_id": entity_id}).rowcount

            # Also cancel the workflow task instances themselves
            if wf_cancelled:
                db.execute(text(f"""
                    UPDATE workflow_task_instances
                    SET status = 'cancelled', updated_at = NOW()
                    WHERE {entity_col} = :entity_id
                    AND status IN ('scheduled', 'pending')
                """), {"entity_id": entity_id})
                logger.info(f"Cancelled {wf_cancelled} workflow tasks for {entity_col}={entity_id} — milestone completed via SLA")

        db.commit()
        result["success"] = True

    except Exception as e:
        db.rollback()
        logger.error(f"Error completing SLA task {task_id}: {e}")
        result["error"] = str(e)

    return result


def get_sla_tasks_for_user(
    db: Session,
    user_id: int,
    include_completed: bool = False
) -> List[Dict[str, Any]]:
    """
    Get all SLA warning tasks for a user.

    Returns list of tasks with SLA milestone information.
    """
    from database.models import Task, Loan, Lead

    query = db.query(Task).filter(
        Task.owner_id == user_id,
        Task.sla_milestone_id.isnot(None)
    )

    if not include_completed:
        query = query.filter(Task.status != "completed")

    tasks = query.order_by(Task.due_date).all()

    result = []
    for task in tasks:
        task_data = {
            "id": task.id,
            "title": task.title,
            "description": task.description,
            "status": task.status,
            "priority": task.priority,
            "due_date": task.due_date.isoformat() if task.due_date else None,
            "sla_milestone_id": task.sla_milestone_id,
            "sla_milestone_type": task.sla_milestone_type,
            "sla_date_field": task.sla_date_field,
            "milestone_date": task.milestone_date.isoformat() if task.milestone_date else None,
            "loan_id": task.loan_id,
            "lead_id": task.lead_id,
            "related_contact_name": task.related_contact_name,
            "created_at": task.created_at.isoformat() if task.created_at else None
        }

        # Add loan info if available
        if task.loan_id:
            loan = db.query(Loan).filter(Loan.id == task.loan_id).first()
            if loan:
                task_data["loan_number"] = loan.loan_number
                task_data["borrower_name"] = loan.borrower_name

        # Add lead info if available
        if task.lead_id:
            lead = db.query(Lead).filter(Lead.id == task.lead_id).first()
            if lead:
                task_data["lead_name"] = f"{lead.first_name} {lead.last_name}"

        result.append(task_data)

    return result
