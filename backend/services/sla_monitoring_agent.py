"""
SLA Monitoring Agent

AI agent that monitors loan lifecycle milestones and creates tasks when SLAs
are at risk (90% threshold) or breached (100%+).

Data Flow:
1. Salesforce syncs milestone dates to Lead/ActiveLoan profiles
2. This agent monitors those dates against SLA measures
3. When thresholds are reached, tasks are created for the appropriate team member

Task Assignment Rules (based on milestone type):
- Lead/Pre-qualification milestones → Loan Officer
- Processing milestones (appraisal, title, insurance) → Processor
- Underwriting milestones → Underwriter
- Closing milestones → Closer
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from enum import Enum
from dataclasses import dataclass

from sqlalchemy import and_, or_, text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class AlertLevel(str, Enum):
    """Alert level for SLA monitoring."""
    AT_RISK = "at_risk"  # 90% of SLA elapsed
    BREACHED = "breached"  # 100%+ of SLA elapsed


@dataclass
class MilestoneCheck:
    """Result of checking a milestone against its SLA."""
    milestone_type: str
    loan_id: Optional[int]
    lead_id: Optional[int]
    loan_number: str
    borrower_name: str
    started_at: datetime
    target_deadline: datetime
    elapsed_hours: float
    target_hours: float
    percent_elapsed: float
    alert_level: Optional[AlertLevel]
    assigned_to_role: str
    assigned_to_id: Optional[int]
    assigned_to_name: Optional[str]


# Mapping of milestone types to team member roles
MILESTONE_ROLE_MAPPING = {
    # Lead Stage - Loan Officer
    "lead_response": "loan_officer",
    "initial_consultation": "loan_officer",
    "pre_qualified": "loan_officer",
    "preapproval": "loan_officer",
    "contract_received": "loan_officer",
    "documents_requested": "loan_officer",
    "documents_received": "loan_officer",
    "application_complete": "loan_officer",

    # Processing Stage - Processor
    "submitted_to_processing": "processor",
    "processing_start": "processor",
    "appraisal_ordered": "processor",
    "appraisal_received": "processor",
    "title_ordered": "processor",
    "title_received": "processor",
    "insurance_ordered": "processor",
    "insurance_received": "processor",
    "flood_insurance_ordered": "processor",
    "flood_insurance_received": "processor",
    "hazard_insurance_ordered": "processor",
    "hazard_insurance_received": "processor",
    "document_collection": "processor",

    # Underwriting Stage - Underwriter
    "submitted_to_uw": "underwriter",
    "uw_decision": "underwriter",
    "approved": "underwriter",
    "conditions_issued": "underwriter",
    "conditions_cleared": "underwriter",

    # Closing Stage - Closer
    "clear_to_close": "closer",
    "closing_docs_out": "closer",
    "closing_scheduled": "closer",
    "closing_date": "closer",
    "closed": "closer",
    "funded": "closer",
}

# Milestone date field mapping (milestone_type -> date field in profile)
MILESTONE_DATE_FIELDS = {
    # Processing log items
    "appraisal_ordered": "appraisal_ordered_date",
    "appraisal_received": "appraisal_received_date",
    "title_ordered": "title_ordered_date",
    "title_received": "title_received_date",
    "insurance_ordered": "hazard_insurance_ordered_date",
    "insurance_received": "hazard_insurance_received_date",
    "flood_insurance_ordered": "flood_insurance_ordered_date",
    "flood_insurance_received": "flood_insurance_received_date",

    # Important dates
    "application_complete": "application_completed_date",
    "pre_qualified": "lead_qualification_date",
    "preapproval": "preapproval_issued_date",
    "contract_received": "contract_received_date",
    "submitted_to_processing": "processor_submission_date",
    "submitted_to_uw": "underwriting_submission_date",
    "approved": "approved_date",
    "conditions_issued": "conditions_sent_date",
    "conditions_cleared": "conditions_received_date",
    "clear_to_close": "clear_to_close_date",
    "closing_docs_out": "docs_out_date",
    "closing_date": "signing_date",
    "funded": "funded_date",
}


class SLAMonitoringAgent:
    """
    Agent that monitors SLA milestones and creates tasks when thresholds are reached.

    Designed to be run periodically (e.g., every 15 minutes) to check for:
    1. Milestones approaching their deadline (90% elapsed)
    2. Milestones that have breached their deadline
    """

    def __init__(self, db: Session, organization_id: int = 1):
        self.db = db
        self.organization_id = organization_id
        self.warning_threshold_pct = 90  # Create task at 90% of SLA
        self.critical_threshold_pct = 100  # Escalate at 100%

    def run_monitoring_cycle(self) -> Dict:
        """
        Run a complete monitoring cycle.

        Returns:
            Dict with monitoring results including tasks created and alerts
        """
        logger.info("Starting SLA monitoring cycle")

        results = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "milestones_checked": 0,
            "at_risk_count": 0,
            "breached_count": 0,
            "tasks_created": 0,
            "alerts": [],
            "errors": []
        }

        try:
            # Get all active SLA measures
            sla_measures = self._get_active_sla_measures()
            logger.info(f"Found {len(sla_measures)} active SLA measures")

            # Get in-progress milestones
            in_progress_milestones = self._get_in_progress_milestones()
            logger.info(f"Found {len(in_progress_milestones)} in-progress milestones")

            results["milestones_checked"] = len(in_progress_milestones)

            # Check each milestone against its SLA
            for milestone in in_progress_milestones:
                try:
                    check_result = self._check_milestone_sla(milestone, sla_measures)

                    if check_result and check_result.alert_level:
                        if check_result.alert_level == AlertLevel.AT_RISK:
                            results["at_risk_count"] += 1
                        elif check_result.alert_level == AlertLevel.BREACHED:
                            results["breached_count"] += 1

                        # Create or update task
                        task_created = self._create_or_update_task(check_result)
                        if task_created:
                            results["tasks_created"] += 1

                        # Create alert record
                        self._create_alert(check_result)

                        results["alerts"].append({
                            "milestone_type": check_result.milestone_type,
                            "loan_number": check_result.loan_number,
                            "borrower": check_result.borrower_name,
                            "alert_level": check_result.alert_level.value,
                            "percent_elapsed": round(check_result.percent_elapsed, 1),
                            "assigned_to": check_result.assigned_to_name,
                        })

                except Exception as e:
                    logger.error(f"Error checking milestone: {e}")
                    results["errors"].append(str(e))

            self.db.commit()
            logger.info(f"SLA monitoring cycle complete: {results['tasks_created']} tasks created")

        except Exception as e:
            logger.error(f"SLA monitoring cycle failed: {e}")
            results["errors"].append(str(e))
            self.db.rollback()

        return results

    def run_monitoring(self) -> Dict:
        """Alias for run_monitoring_cycle for API compatibility."""
        return self.run_monitoring_cycle()

    def get_monitoring_status(self) -> Dict:
        """
        Get current monitoring status without creating tasks.

        Returns summary of milestones at risk and overdue.
        """
        from models.sla_tracking import LoanMilestoneHistory, SLAStatus

        status = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_active": 0,
            "at_risk": [],
            "overdue": [],
            "recent_tasks": []
        }

        try:
            # Get SLA measures
            sla_measures = self._get_active_sla_measures()

            # Get in-progress milestones
            milestones = self._get_in_progress_milestones()
            status["total_active"] = len(milestones)

            # Check each milestone
            for milestone in milestones:
                check = self._check_milestone_sla(milestone, sla_measures)
                if check and check.alert_level:
                    item = {
                        "milestone_type": check.milestone_type,
                        "loan_number": check.loan_number,
                        "borrower": check.borrower_name,
                        "percent_elapsed": round(check.percent_elapsed, 1),
                        "hours_remaining": round(check.target_hours - check.elapsed_hours, 1),
                        "assigned_to": check.assigned_to_name,
                    }
                    if check.alert_level == AlertLevel.BREACHED:
                        status["overdue"].append(item)
                    else:
                        status["at_risk"].append(item)

            # Get recent SLA-related tasks
            recent_tasks = self.db.execute(
                text("""
                    SELECT title, status, priority, created_at, owner_id
                    FROM tasks
                    WHERE related_type = 'sla_alert'
                    AND created_at >= NOW() - INTERVAL '24 hours'
                    ORDER BY created_at DESC
                    LIMIT 10
                """)
            ).fetchall()

            status["recent_tasks"] = [
                {
                    "title": t[0],
                    "status": t[1],
                    "priority": t[2],
                    "created_at": t[3].isoformat() if t[3] else None,
                }
                for t in recent_tasks
            ]

        except Exception as e:
            logger.error(f"Error getting monitoring status: {e}")
            status["error"] = str(e)

        return status

    def _get_active_sla_measures(self) -> List[Dict]:
        """Get all active SLA measures from the database."""
        from models.sla_tracking import SLAMeasure

        measures = self.db.query(SLAMeasure).filter(
            SLAMeasure.is_active == True,
            SLAMeasure.organization_id == self.organization_id
        ).all()

        return {m.milestone_type.value: m for m in measures}

    def _get_in_progress_milestones(self) -> List[Dict]:
        """Get all in-progress milestones from loan_milestone_history."""
        from models.sla_tracking import LoanMilestoneHistory, SLAStatus

        milestones = self.db.query(LoanMilestoneHistory).filter(
            LoanMilestoneHistory.organization_id == self.organization_id,
            LoanMilestoneHistory.status.in_([
                SLAStatus.IN_PROGRESS,
                SLAStatus.ON_TRACK,
                SLAStatus.AT_RISK
            ]),
            LoanMilestoneHistory.completed_at.is_(None)
        ).all()

        return milestones

    def _check_milestone_sla(
        self,
        milestone,
        sla_measures: Dict
    ) -> Optional[MilestoneCheck]:
        """
        Check a milestone against its SLA target.

        Returns MilestoneCheck if the milestone is at risk or breached, None otherwise.
        """
        milestone_type = milestone.milestone_type.value

        if milestone_type not in sla_measures:
            return None

        sla_measure = sla_measures[milestone_type]

        if not milestone.started_at:
            return None

        # Calculate elapsed time
        now = datetime.now(timezone.utc)
        started = milestone.started_at
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)

        elapsed = now - started
        elapsed_hours = elapsed.total_seconds() / 3600

        # Get target hours
        target_hours = self._get_target_hours(sla_measure)

        if target_hours <= 0:
            return None

        # Calculate percentage
        percent_elapsed = (elapsed_hours / target_hours) * 100

        # Determine alert level
        alert_level = None
        if percent_elapsed >= self.critical_threshold_pct:
            alert_level = AlertLevel.BREACHED
        elif percent_elapsed >= self.warning_threshold_pct:
            alert_level = AlertLevel.AT_RISK

        if not alert_level:
            return None

        # Get loan/lead details and team member assignment
        loan_info = self._get_loan_info(milestone.loan_id, milestone.lead_id)
        assigned_role = MILESTONE_ROLE_MAPPING.get(milestone_type, "processor")
        assigned_to = self._get_team_member(
            milestone.loan_id,
            milestone.lead_id,
            assigned_role
        )

        return MilestoneCheck(
            milestone_type=milestone_type,
            loan_id=milestone.loan_id,
            lead_id=milestone.lead_id,
            loan_number=loan_info.get("loan_number", ""),
            borrower_name=loan_info.get("borrower_name", ""),
            started_at=started,
            target_deadline=started + timedelta(hours=target_hours),
            elapsed_hours=elapsed_hours,
            target_hours=target_hours,
            percent_elapsed=percent_elapsed,
            alert_level=alert_level,
            assigned_to_role=assigned_role,
            assigned_to_id=assigned_to.get("id"),
            assigned_to_name=assigned_to.get("name"),
        )

    def _get_target_hours(self, sla_measure) -> float:
        """Convert SLA target to hours."""
        from models.sla_tracking import TimeUnit

        value = sla_measure.target_value
        unit = sla_measure.target_unit

        if unit == TimeUnit.HOURS:
            return value
        elif unit == TimeUnit.DAYS:
            return value * 24
        elif unit == TimeUnit.BUSINESS_DAYS:
            return value * 8  # Assuming 8-hour business day

        return value

    def _get_loan_info(self, loan_id: Optional[int], lead_id: Optional[int]) -> Dict:
        """Get loan/lead information for task creation."""
        info = {"loan_number": "", "borrower_name": ""}

        if loan_id:
            # Query from loans table
            result = self.db.execute(
                text("SELECT loan_number, borrower_name FROM loans WHERE id = :id"),
                {"id": loan_id}
            ).fetchone()
            if result:
                info["loan_number"] = result[0] or ""
                info["borrower_name"] = result[1] or ""
        elif lead_id:
            # Query from leads table
            result = self.db.execute(
                text("SELECT loan_number, first_name, last_name FROM leads WHERE id = :id"),
                {"id": lead_id}
            ).fetchone()
            if result:
                info["loan_number"] = result[0] or ""
                info["borrower_name"] = f"{result[1] or ''} {result[2] or ''}".strip()

        return info

    def _get_team_member(
        self,
        loan_id: Optional[int],
        lead_id: Optional[int],
        role: str
    ) -> Dict:
        """
        Get the team member for a specific role from the loan/lead profile.

        Roles: loan_officer, processor, underwriter, closer
        """
        team_member = {"id": None, "name": None}

        # Field mapping for role to database column
        role_field_map = {
            "loan_officer": ("loan_officer_id", "loan_officer_name"),
            "processor": ("processor_id", "processor"),
            "underwriter": ("underwriter_id", "underwriter"),
            "closer": ("closer_id", "closer"),
        }

        id_field, name_field = role_field_map.get(role, ("loan_officer_id", "loan_officer_name"))

        if loan_id:
            # Try active_loan_profiles first
            result = self.db.execute(
                text(f"""
                    SELECT {name_field}
                    FROM active_loan_profiles
                    WHERE id = :id OR lead_profile_id = (
                        SELECT id FROM lead_profiles WHERE id = :id
                    )
                    LIMIT 1
                """),
                {"id": loan_id}
            ).fetchone()

            if result and result[0]:
                team_member["name"] = result[0]
                # Try to find user ID by name
                user = self.db.execute(
                    text("SELECT id FROM users WHERE name = :name LIMIT 1"),
                    {"name": result[0]}
                ).fetchone()
                if user:
                    team_member["id"] = user[0]

        elif lead_id:
            # Try lead_profiles
            result = self.db.execute(
                text(f"SELECT {name_field.replace('_name', '')} FROM lead_profiles WHERE id = :id"),
                {"id": lead_id}
            ).fetchone()

            if result and result[0]:
                team_member["name"] = result[0]
                user = self.db.execute(
                    text("SELECT id FROM users WHERE name = :name LIMIT 1"),
                    {"name": result[0]}
                ).fetchone()
                if user:
                    team_member["id"] = user[0]

        return team_member

    def _create_or_update_task(self, check: MilestoneCheck) -> bool:
        """
        Create a task for the SLA alert, or update existing if one exists.

        Returns True if a new task was created.
        """
        # Check if task already exists for this milestone
        existing_task = self.db.execute(
            text("""
                SELECT id FROM tasks
                WHERE sla_milestone_type = :milestone_type
                AND (loan_id = :loan_id OR lead_id = :lead_id)
                AND status != 'completed'
                LIMIT 1
            """),
            {
                "milestone_type": check.milestone_type,
                "loan_id": check.loan_id,
                "lead_id": check.lead_id
            }
        ).fetchone()

        if existing_task:
            # Update existing task priority if breached
            if check.alert_level == AlertLevel.BREACHED:
                self.db.execute(
                    text("""
                        UPDATE tasks
                        SET priority = 'high',
                            updated_at = NOW(),
                            description = :description
                        WHERE id = :id
                    """),
                    {
                        "id": existing_task[0],
                        "description": self._generate_task_description(check)
                    }
                )
            return False

        # Create new task
        priority = "high" if check.alert_level == AlertLevel.BREACHED else "medium"

        milestone_label = check.milestone_type.replace("_", " ").title()
        if check.alert_level == AlertLevel.BREACHED:
            title = f"OVERDUE: {milestone_label} - {check.borrower_name}"
        else:
            title = f"At Risk: {milestone_label} - {check.borrower_name}"

        self.db.execute(
            text("""
                INSERT INTO tasks (
                    title, description, status, priority, due_date,
                    owner_id, loan_id, lead_id, related_contact_name,
                    related_type, sla_milestone_type, sla_date_field,
                    created_at, updated_at
                ) VALUES (
                    :title, :description, 'pending', :priority, :due_date,
                    :owner_id, :loan_id, :lead_id, :contact_name,
                    'sla_alert', :milestone_type, :date_field,
                    NOW(), NOW()
                )
            """),
            {
                "title": title,
                "description": self._generate_task_description(check),
                "priority": priority,
                "due_date": check.target_deadline,
                "owner_id": check.assigned_to_id,
                "loan_id": check.loan_id,
                "lead_id": check.lead_id,
                "contact_name": check.borrower_name,
                "milestone_type": check.milestone_type,
                "date_field": MILESTONE_DATE_FIELDS.get(check.milestone_type),
            }
        )

        logger.info(f"Created SLA task: {title} assigned to {check.assigned_to_name}")
        return True

    def _generate_task_description(self, check: MilestoneCheck) -> str:
        """Generate task description with context."""
        milestone_label = check.milestone_type.replace("_", " ").title()

        if check.alert_level == AlertLevel.BREACHED:
            status = f"**OVERDUE** - {round(check.percent_elapsed - 100, 1)}% over deadline"
        else:
            status = f"**At Risk** - {round(check.percent_elapsed, 1)}% of SLA time elapsed"

        return f"""
{status}

**Milestone:** {milestone_label}
**Loan Number:** {check.loan_number}
**Borrower:** {check.borrower_name}

**Timeline:**
- Started: {check.started_at.strftime('%m/%d/%Y %I:%M %p')}
- Target Deadline: {check.target_deadline.strftime('%m/%d/%Y %I:%M %p')}
- Time Elapsed: {round(check.elapsed_hours, 1)} hours
- Target Time: {round(check.target_hours, 1)} hours

**Action Required:**
Complete the {milestone_label.lower()} milestone or update status if delayed.
""".strip()

    def _create_alert(self, check: MilestoneCheck):
        """Create an SLA alert record."""
        from models.sla_tracking import SLAAlert, AlertStatus

        alert_type = "critical" if check.alert_level == AlertLevel.BREACHED else "warning"
        milestone_label = check.milestone_type.replace("_", " ").title()

        if check.alert_level == AlertLevel.BREACHED:
            title = f"SLA Breached: {milestone_label}"
            message = f"{milestone_label} is {round(check.percent_elapsed - 100, 1)}% over deadline for {check.borrower_name}"
        else:
            title = f"SLA At Risk: {milestone_label}"
            message = f"{milestone_label} is at {round(check.percent_elapsed, 1)}% of target time for {check.borrower_name}"

        # Check if alert already exists
        existing = self.db.execute(
            text("""
                SELECT id FROM sla_alerts
                WHERE milestone_type = :milestone_type
                AND (loan_id = :loan_id OR lead_id = :lead_id)
                AND status = 'active'
                LIMIT 1
            """),
            {
                "milestone_type": check.milestone_type,
                "loan_id": check.loan_id,
                "lead_id": check.lead_id
            }
        ).fetchone()

        if existing:
            # Update existing alert
            self.db.execute(
                text("""
                    UPDATE sla_alerts
                    SET alert_type = :alert_type,
                        title = :title,
                        message = :message,
                        updated_at = NOW()
                    WHERE id = :id
                """),
                {
                    "id": existing[0],
                    "alert_type": alert_type,
                    "title": title,
                    "message": message
                }
            )
        else:
            # Create new alert
            self.db.execute(
                text("""
                    INSERT INTO sla_alerts (
                        organization_id, milestone_history_id, loan_id, lead_id,
                        alert_type, milestone_type, title, message,
                        status, assigned_to_id, triggered_at, created_at, updated_at
                    ) VALUES (
                        :org_id, NULL, :loan_id, :lead_id,
                        :alert_type, :milestone_type, :title, :message,
                        'active', :assigned_to, NOW(), NOW(), NOW()
                    )
                """),
                {
                    "org_id": self.organization_id,
                    "loan_id": check.loan_id,
                    "lead_id": check.lead_id,
                    "alert_type": alert_type,
                    "milestone_type": check.milestone_type,
                    "title": title,
                    "message": message,
                    "assigned_to": check.assigned_to_id
                }
            )


def run_sla_monitoring(db: Session, organization_id: int = 1) -> Dict:
    """
    Convenience function to run SLA monitoring.
    Can be called from a scheduler or API endpoint.
    """
    agent = SLAMonitoringAgent(db, organization_id)
    return agent.run_monitoring_cycle()


# Scheduled task function for use with APScheduler or similar
async def scheduled_sla_monitoring():
    """
    Scheduled task to run SLA monitoring.
    Should be called every 15 minutes or as needed.
    """
    from database import SessionLocal

    db = SessionLocal()
    try:
        results = run_sla_monitoring(db)
        logger.info(f"Scheduled SLA monitoring complete: {results}")
        return results
    finally:
        db.close()
