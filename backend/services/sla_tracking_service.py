"""
SLA Tracking Service

Provides automatic SLA tracking through event listeners and helper functions.
Integrates with loan/lead status changes to automatically start/complete milestones.
"""

import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import event

from models.sla_tracking import (
    SLAMeasure,
    LoanMilestoneHistory,
    SLAAlert,
    SLAStatus,
    MilestoneType,
    AlertStatus
)
from crud.sla_tracking import (
    create_milestone_history,
    complete_milestone,
    get_loan_milestones,
    get_sla_measure_by_type,
    create_sla_alert,
    update_milestone_status
)
from schemas.sla_tracking import SLAAlertCreate
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


# ============================================================================
# Stage to Milestone Mapping
# ============================================================================

# Maps loan/lead stages to milestone types for auto-tracking
LEAD_STAGE_TO_MILESTONE = {
    "new": MilestoneType.LEAD_RESPONSE,
    "contacted": MilestoneType.LEAD_RESPONSE,
    "pre_qualified": MilestoneType.PRE_QUALIFIED,
    "pre_approved": MilestoneType.PREAPPROVAL,
    "pre-approved": MilestoneType.PREAPPROVAL,
    "documents_requested": MilestoneType.DOCUMENTS_REQUESTED,
    "documents_received": MilestoneType.DOCUMENTS_RECEIVED,
    "application_complete": MilestoneType.APPLICATION_COMPLETE,
    "application_completed": MilestoneType.APPLICATION_COMPLETE,
}

LOAN_STAGE_TO_MILESTONE = {
    "application": MilestoneType.APPLICATION_SUBMITTED,
    "application_submitted": MilestoneType.APPLICATION_SUBMITTED,
    "le_pending": MilestoneType.LE_PENDING,
    "disclosed": MilestoneType.LE_DISCLOSED,
    "le_disclosed": MilestoneType.LE_DISCLOSED,
    "processing": MilestoneType.PROCESSING_START,
    "in_processing": MilestoneType.PROCESSING_START,
    "submitted": MilestoneType.SUBMITTED_TO_UW,
    "submitted_to_uw": MilestoneType.SUBMITTED_TO_UW,
    "uw_received": MilestoneType.SUBMITTED_TO_UW,
    "underwriting": MilestoneType.UW_DECISION,
    "approved": MilestoneType.APPROVED,
    "conditional_approval": MilestoneType.CONDITIONS_ISSUED,
    "conditions_pending": MilestoneType.CONDITIONS_CLEARED,
    "ctc": MilestoneType.CLEAR_TO_CLOSE,
    "clear_to_close": MilestoneType.CLEAR_TO_CLOSE,
    "docs_out": MilestoneType.CLOSING_DOCS_OUT,
    "closing_scheduled": MilestoneType.CLOSING_SCHEDULED,
    "closed": MilestoneType.CLOSED,
    "funded": MilestoneType.FUNDED,
}

# Milestone completion triggers (when entering these stages, complete previous milestone)
MILESTONE_COMPLETION_MAP = {
    # Lead Stage progression
    MilestoneType.PRE_QUALIFIED: MilestoneType.LEAD_RESPONSE,
    MilestoneType.PREAPPROVAL: MilestoneType.PRE_QUALIFIED,
    MilestoneType.DOCUMENTS_REQUESTED: MilestoneType.PREAPPROVAL,
    MilestoneType.DOCUMENTS_RECEIVED: MilestoneType.DOCUMENTS_REQUESTED,
    MilestoneType.APPLICATION_COMPLETE: MilestoneType.DOCUMENTS_RECEIVED,
    # Active Loan Stage progression
    MilestoneType.APPLICATION_SUBMITTED: MilestoneType.APPLICATION_COMPLETE,
    MilestoneType.LE_PENDING: MilestoneType.APPLICATION_SUBMITTED,
    MilestoneType.LE_DISCLOSED: MilestoneType.LE_PENDING,
    MilestoneType.PROCESSING_START: MilestoneType.LE_DISCLOSED,
    MilestoneType.SUBMITTED_TO_UW: MilestoneType.PROCESSING_START,
    MilestoneType.UW_DECISION: MilestoneType.SUBMITTED_TO_UW,
    MilestoneType.CONDITIONS_CLEARED: MilestoneType.CONDITIONS_ISSUED,
    MilestoneType.CLEAR_TO_CLOSE: MilestoneType.CONDITIONS_CLEARED,
    MilestoneType.CLOSING_DOCS_OUT: MilestoneType.CLEAR_TO_CLOSE,
    MilestoneType.CLOSED: MilestoneType.CLOSING_SCHEDULED,
    MilestoneType.FUNDED: MilestoneType.CLOSED,
}


class SLATrackingService:
    """
    Service for automatic SLA tracking.
    Provides methods to track milestones based on loan/lead events.
    """

    def __init__(self, db: Session, organization_id: int = None):
        self.db = db
        self.organization_id = organization_id

    def on_lead_created(self, lead_id: int, loan_number: Optional[str] = None):
        """
        Called when a new lead is created.
        Starts the LEAD_RESPONSE milestone timer.
        """
        try:
            milestone = create_milestone_history(
                self.db,
                lead_id=lead_id,
                loan_number=loan_number,
                milestone_type=MilestoneType.LEAD_RESPONSE,
                organization_id=self.organization_id
            )
            if milestone:
                logger.info(f"Started LEAD_RESPONSE milestone for lead {lead_id}")
                return milestone.id
        except Exception as e:
            logger.error(f"Error starting lead response milestone: {e}")
        return None

    def on_lead_stage_change(
        self,
        lead_id: int,
        old_stage: Optional[str],
        new_stage: str,
        user_id: Optional[int] = None,
        loan_number: Optional[str] = None
    ):
        """
        Called when a lead's stage changes.
        Completes previous milestones and starts new ones.
        """
        try:
            new_stage_lower = new_stage.lower().replace(" ", "_")

            # Check if new stage maps to a milestone
            new_milestone_type = LEAD_STAGE_TO_MILESTONE.get(new_stage_lower)

            if new_milestone_type:
                # Complete the previous milestone if exists
                prev_milestone_type = MILESTONE_COMPLETION_MAP.get(new_milestone_type)
                if prev_milestone_type:
                    self._complete_milestone_by_type(
                        lead_id=lead_id,
                        milestone_type=prev_milestone_type,
                        completed_by_id=user_id
                    )

                # Start the new milestone
                self._start_milestone(
                    lead_id=lead_id,
                    loan_number=loan_number,
                    milestone_type=new_milestone_type,
                    assigned_to_id=user_id
                )

            logger.info(f"Processed lead stage change: {old_stage} -> {new_stage} for lead {lead_id}")

        except Exception as e:
            logger.error(f"Error processing lead stage change: {e}")

    def on_loan_created(
        self,
        loan_id: int,
        loan_number: str,
        lead_id: Optional[int] = None
    ):
        """
        Called when a new loan is created (application submitted).
        Starts APPLICATION_SUBMITTED milestone.
        """
        try:
            # Complete any outstanding lead milestones if lead_id is provided
            if lead_id:
                # Complete PREAPPROVAL milestone
                self._complete_milestone_by_type(
                    lead_id=lead_id,
                    milestone_type=MilestoneType.PREAPPROVAL
                )

            # Start application submitted milestone
            milestone = create_milestone_history(
                self.db,
                loan_id=loan_id,
                loan_number=loan_number,
                milestone_type=MilestoneType.APPLICATION_SUBMITTED,
                organization_id=self.organization_id
            )
            if milestone:
                logger.info(f"Started APPLICATION_SUBMITTED milestone for loan {loan_id}")
                return milestone.id

        except Exception as e:
            logger.error(f"Error starting loan milestone: {e}")
        return None

    def on_loan_stage_change(
        self,
        loan_id: int,
        old_stage: Optional[str],
        new_stage: str,
        user_id: Optional[int] = None,
        loan_number: Optional[str] = None
    ):
        """
        Called when a loan's stage changes.
        Completes previous milestones and starts new ones.
        """
        try:
            new_stage_lower = new_stage.lower().replace(" ", "_")

            # Check if new stage maps to a milestone
            new_milestone_type = LOAN_STAGE_TO_MILESTONE.get(new_stage_lower)

            if new_milestone_type:
                # Complete the previous milestone if exists
                prev_milestone_type = MILESTONE_COMPLETION_MAP.get(new_milestone_type)
                if prev_milestone_type:
                    self._complete_milestone_by_type(
                        loan_id=loan_id,
                        milestone_type=prev_milestone_type,
                        completed_by_id=user_id
                    )

                # Start the new milestone
                self._start_milestone(
                    loan_id=loan_id,
                    loan_number=loan_number,
                    milestone_type=new_milestone_type,
                    assigned_to_id=user_id
                )

            logger.info(f"Processed loan stage change: {old_stage} -> {new_stage} for loan {loan_id}")

        except Exception as e:
            logger.error(f"Error processing loan stage change: {e}")

    def on_appraisal_ordered(self, loan_id: int, loan_number: Optional[str] = None):
        """Called when appraisal is ordered."""
        self._start_milestone(loan_id, loan_number, MilestoneType.APPRAISAL_ORDERED)

    def on_appraisal_received(self, loan_id: int, user_id: Optional[int] = None):
        """Called when appraisal is received."""
        self._complete_milestone_by_type(loan_id, MilestoneType.APPRAISAL_ORDERED, user_id)
        self._start_milestone(loan_id, None, MilestoneType.APPRAISAL_RECEIVED)
        self._complete_milestone_by_type(loan_id, MilestoneType.APPRAISAL_RECEIVED, user_id)

    def on_title_ordered(self, loan_id: int, loan_number: Optional[str] = None):
        """Called when title is ordered."""
        self._start_milestone(loan_id, loan_number, MilestoneType.TITLE_ORDERED)

    def on_title_received(self, loan_id: int, user_id: Optional[int] = None):
        """Called when title is received."""
        self._complete_milestone_by_type(loan_id, MilestoneType.TITLE_ORDERED, user_id)
        self._start_milestone(loan_id, None, MilestoneType.TITLE_RECEIVED)
        self._complete_milestone_by_type(loan_id, MilestoneType.TITLE_RECEIVED, user_id)

    def on_conditions_issued(self, loan_id: int, loan_number: Optional[str] = None):
        """Called when conditions are issued."""
        self._complete_milestone_by_type(loan_id, MilestoneType.UW_DECISION)
        self._start_milestone(loan_id, loan_number, MilestoneType.CONDITIONS_ISSUED)

    def on_document_collected(
        self,
        loan_id: int,
        document_type: str,
        loan_number: Optional[str] = None
    ):
        """
        Called when a document is collected.
        Could be used for fine-grained document tracking.
        """
        # This could track individual document milestones
        logger.info(f"Document collected for loan {loan_id}: {document_type}")

    def _start_milestone(
        self,
        loan_id: Optional[int] = None,
        loan_number: Optional[str] = None,
        milestone_type: MilestoneType = None,
        lead_id: Optional[int] = None,
        assigned_to_id: Optional[int] = None
    ) -> Optional[int]:
        """Start tracking a milestone."""
        try:
            # Check if milestone already exists and is active
            existing = self._get_active_milestone(
                loan_id=loan_id,
                lead_id=lead_id,
                milestone_type=milestone_type
            )
            if existing:
                logger.debug(f"Milestone {milestone_type} already active for loan/lead")
                return existing.id

            milestone = create_milestone_history(
                self.db,
                loan_id=loan_id,
                lead_id=lead_id,
                loan_number=loan_number,
                milestone_type=milestone_type,
                assigned_to_id=assigned_to_id,
                organization_id=self.organization_id
            )
            if milestone:
                logger.info(f"Started {milestone_type.value} milestone")
                return milestone.id
        except Exception as e:
            logger.error(f"Error starting milestone {milestone_type}: {e}")
        return None

    def _complete_milestone_by_type(
        self,
        loan_id: Optional[int] = None,
        milestone_type: MilestoneType = None,
        completed_by_id: Optional[int] = None,
        lead_id: Optional[int] = None
    ) -> bool:
        """Complete a milestone by type (find active one and complete it)."""
        try:
            milestone = self._get_active_milestone(
                loan_id=loan_id,
                lead_id=lead_id,
                milestone_type=milestone_type
            )
            if milestone:
                result = complete_milestone(
                    self.db,
                    milestone.id,
                    completed_by_id=completed_by_id,
                    organization_id=self.organization_id
                )
                if result:
                    # Check if completed late and create alert if needed
                    if result.variance_hours and result.variance_hours > 0:
                        self._create_late_completion_alert(result)
                    logger.info(f"Completed {milestone_type.value} milestone")
                    return True
        except Exception as e:
            logger.error(f"Error completing milestone {milestone_type}: {e}")
        return False

    def _get_active_milestone(
        self,
        loan_id: Optional[int] = None,
        lead_id: Optional[int] = None,
        milestone_type: Optional[MilestoneType] = None
    ) -> Optional[LoanMilestoneHistory]:
        """Find an active milestone for a loan/lead."""
        query = self.db.query(LoanMilestoneHistory).filter(
            LoanMilestoneHistory.organization_id == self.organization_id,
            LoanMilestoneHistory.status.in_([
                SLAStatus.IN_PROGRESS,
                SLAStatus.ON_TRACK,
                SLAStatus.AT_RISK,
                SLAStatus.OVERDUE
            ])
        )
        if loan_id:
            query = query.filter(LoanMilestoneHistory.loan_id == loan_id)
        if lead_id:
            query = query.filter(LoanMilestoneHistory.lead_id == lead_id)
        if milestone_type:
            query = query.filter(LoanMilestoneHistory.milestone_type == milestone_type)

        return query.first()

    def _create_late_completion_alert(self, milestone: LoanMilestoneHistory):
        """Create an alert for late milestone completion."""
        try:
            alert_data = SLAAlertCreate(
                milestone_history_id=milestone.id,
                loan_id=milestone.loan_id,
                lead_id=milestone.lead_id,
                alert_type="late_completion",
                milestone_type=milestone.milestone_type,
                title=f"Late: {milestone.milestone_type.value.replace('_', ' ').title()}",
                message=f"Milestone completed {abs(milestone.variance_hours):.1f} hours late ({milestone.variance_pct:.1f}% over target)",
                assigned_to_id=milestone.assigned_to_id
            )
            create_sla_alert(self.db, alert_data, self.organization_id)
        except Exception as e:
            logger.error(f"Error creating late completion alert: {e}")

    def check_and_create_risk_alerts(self):
        """
        Check active milestones and create alerts for at-risk/overdue items.
        Called by background job.
        """
        try:
            # Get at-risk milestones without existing active alerts
            at_risk = self.db.query(LoanMilestoneHistory).filter(
                LoanMilestoneHistory.organization_id == self.organization_id,
                LoanMilestoneHistory.status == SLAStatus.AT_RISK
            ).all()

            for milestone in at_risk:
                # Check if alert already exists
                existing_alert = self.db.query(SLAAlert).filter(
                    SLAAlert.milestone_history_id == milestone.id,
                    SLAAlert.alert_type == "at_risk",
                    SLAAlert.status == AlertStatus.ACTIVE
                ).first()

                if not existing_alert:
                    alert_data = SLAAlertCreate(
                        milestone_history_id=milestone.id,
                        loan_id=milestone.loan_id,
                        lead_id=milestone.lead_id,
                        alert_type="at_risk",
                        milestone_type=milestone.milestone_type,
                        title=f"At Risk: {milestone.milestone_type.value.replace('_', ' ').title()}",
                        message=f"Milestone approaching deadline. Target: {milestone.target_deadline}",
                        assigned_to_id=milestone.assigned_to_id
                    )
                    create_sla_alert(self.db, alert_data, self.organization_id)

            # Get overdue milestones
            overdue = self.db.query(LoanMilestoneHistory).filter(
                LoanMilestoneHistory.organization_id == self.organization_id,
                LoanMilestoneHistory.status == SLAStatus.OVERDUE
            ).all()

            for milestone in overdue:
                # Check if alert already exists
                existing_alert = self.db.query(SLAAlert).filter(
                    SLAAlert.milestone_history_id == milestone.id,
                    SLAAlert.alert_type == "overdue",
                    SLAAlert.status == AlertStatus.ACTIVE
                ).first()

                if not existing_alert:
                    alert_data = SLAAlertCreate(
                        milestone_history_id=milestone.id,
                        loan_id=milestone.loan_id,
                        lead_id=milestone.lead_id,
                        alert_type="overdue",
                        milestone_type=milestone.milestone_type,
                        title=f"OVERDUE: {milestone.milestone_type.value.replace('_', ' ').title()}",
                        message=f"Milestone is past deadline! Was due: {milestone.target_deadline}",
                        assigned_to_id=milestone.assigned_to_id
                    )
                    create_sla_alert(self.db, alert_data, self.organization_id)

            logger.info(f"Risk alert check complete: {len(at_risk)} at-risk, {len(overdue)} overdue")

        except Exception as e:
            logger.error(f"Error checking risk alerts: {e}")

    def get_loan_sla_summary(self, loan_id: int) -> Dict[str, Any]:
        """Get SLA summary for a specific loan."""
        milestones = get_loan_milestones(self.db, loan_id=loan_id)

        total = len(milestones)
        completed = len([m for m in milestones if m.status == SLAStatus.COMPLETED])
        on_time = len([m for m in milestones if m.status == SLAStatus.COMPLETED and m.variance_hours and m.variance_hours <= 0])
        at_risk = len([m for m in milestones if m.status == SLAStatus.AT_RISK])
        overdue = len([m for m in milestones if m.status == SLAStatus.OVERDUE])

        # Find next deadline
        active_milestones = [m for m in milestones if m.status in [SLAStatus.IN_PROGRESS, SLAStatus.ON_TRACK, SLAStatus.AT_RISK]]
        next_deadline = min((m.target_deadline for m in active_milestones if m.target_deadline), default=None)

        return {
            "loan_id": loan_id,
            "total_milestones": total,
            "completed": completed,
            "on_time": on_time,
            "at_risk": at_risk,
            "overdue": overdue,
            "on_time_rate": (on_time / completed * 100) if completed > 0 else 0,
            "next_deadline": next_deadline,
            "milestones": milestones
        }


# ============================================================================
# Helper function to get service instance
# ============================================================================

def get_sla_service(db: Session, organization_id: int = None) -> SLATrackingService:
    """Get an SLA tracking service instance."""
    return SLATrackingService(db, organization_id=organization_id)


# ============================================================================
# Event hook functions for integration with main app
# ============================================================================

def track_lead_created(db: Session, lead_id: int, loan_number: Optional[str] = None, organization_id: int = None):
    """Hook for lead creation - call from lead creation endpoint."""
    service = get_sla_service(db, organization_id=organization_id)
    return service.on_lead_created(lead_id, loan_number)


def track_lead_stage_change(
    db: Session,
    lead_id: int,
    old_stage: Optional[str],
    new_stage: str,
    user_id: Optional[int] = None,
    loan_number: Optional[str] = None,
    organization_id: int = None
):
    """Hook for lead stage change - call from lead update endpoint."""
    service = get_sla_service(db, organization_id=organization_id)
    return service.on_lead_stage_change(lead_id, old_stage, new_stage, user_id, loan_number)


def track_loan_created(
    db: Session,
    loan_id: int,
    loan_number: str,
    lead_id: Optional[int] = None,
    organization_id: int = None
):
    """Hook for loan creation - call from loan creation endpoint."""
    service = get_sla_service(db, organization_id=organization_id)
    return service.on_loan_created(loan_id, loan_number, lead_id)


def track_loan_stage_change(
    db: Session,
    loan_id: int,
    old_stage: Optional[str],
    new_stage: str,
    user_id: Optional[int] = None,
    loan_number: Optional[str] = None,
    organization_id: int = None
):
    """Hook for loan stage change - call from loan update endpoint."""
    service = get_sla_service(db, organization_id=organization_id)
    return service.on_loan_stage_change(loan_id, old_stage, new_stage, user_id, loan_number)
