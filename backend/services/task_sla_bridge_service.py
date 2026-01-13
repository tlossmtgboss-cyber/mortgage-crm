"""
Task-SLA Bridge Service

Connects workflow task completion to SLA milestone tracking and loan date field updates.
When a user completes a workflow task (e.g., "Order Title"), this service:
1. Finds the associated SLA milestone
2. Marks the milestone as completed
3. Updates the loan's Important Dates field

This bridges the gap between:
- Workflow tasks (what users see and complete)
- SLA milestones (compliance tracking)
- Loan date fields (Salesforce-synced important dates)
"""

import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)


# ============================================================================
# Task Type to SLA Milestone Mapping
# Maps workflow task types/names to their corresponding SLA milestone types
# ============================================================================

TASK_TO_MILESTONE_MAP = {
    # Title milestones
    "title_ordered": "title_ordered",
    "order_title": "title_ordered",
    "title_received": "title_received",

    # Appraisal milestones
    "appraisal_ordered": "appraisal_ordered",
    "order_appraisal": "appraisal_ordered",
    "appraisal_received": "appraisal_received",

    # Insurance milestones
    "insurance_ordered": "insurance_ordered",
    "order_insurance": "insurance_ordered",
    "insurance_received": "insurance_received",

    # Disclosure milestones
    "le_sent": "le_disclosed",
    "send_le": "le_disclosed",
    "cd_sent": "cd_sent",
    "send_cd": "cd_sent",

    # Underwriting milestones
    "submit_to_uw": "submitted_to_uw",
    "submitted_to_uw": "submitted_to_uw",
    "uw_decision": "uw_decision",
    "conditions_issued": "conditions_issued",
    "conditions_cleared": "conditions_cleared",
    "clear_conditions": "conditions_cleared",

    # Closing milestones
    "clear_to_close": "clear_to_close",
    "closing_scheduled": "closing_scheduled",
    "schedule_closing": "closing_scheduled",
    "docs_out": "closing_docs_out",
    "send_docs": "closing_docs_out",
    "funded": "funded",
}

# Milestone type to loan date field mapping
# Same as in crud/sla_tracking.py but we keep a copy here for direct loan updates
MILESTONE_TO_LOAN_FIELD = {
    "appraisal_ordered": "appraisal_ordered_date",
    "appraisal_received": "appraisal_completed_date",
    "title_ordered": "title_ordered_date",
    "title_received": "title_received_date",
    "insurance_ordered": "insurance_ordered_date",
    "insurance_received": "insurance_received_date",
    "le_disclosed": "initial_disclosures_sent_date",
    "cd_sent": "closing_disclosure_sent_date",
    "submitted_to_uw": "submitted_to_uw_date",
    "uw_decision": "uw_decision_date",
    "conditions_issued": "conditional_approval_date",
    "conditions_cleared": "conditions_cleared_date",
    "clear_to_close": "clear_to_close_date",
    "closing_docs_out": "final_closing_package_sent_date",
    "closing_scheduled": "closing_date",
    "funded": "funded_date",
}


class TaskSLABridgeService:
    """
    Service that bridges workflow task completion to SLA milestone tracking.

    When a task is completed, this service:
    1. Identifies the milestone type from the task
    2. Completes the SLA milestone in loan_milestone_history
    3. Updates the loan's Important Dates field
    """

    def __init__(self, db: Session):
        self.db = db

    def on_task_completed(
        self,
        task_instance_id: int,
        completed_by_id: Optional[int] = None,
        notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Called when a workflow task is completed.
        Updates SLA tracking and loan date fields.

        Args:
            task_instance_id: The workflow task instance ID
            completed_by_id: User who completed the task
            notes: Optional completion notes

        Returns:
            Dict with results of SLA updates
        """
        result = {
            "task_instance_id": task_instance_id,
            "milestone_completed": False,
            "loan_date_updated": False,
            "errors": []
        }

        try:
            # Get task instance details
            task_data = self._get_task_instance(task_instance_id)
            if not task_data:
                result["errors"].append("Task instance not found")
                return result

            # Determine milestone type from task
            milestone_type = self._determine_milestone_type(task_data)
            if not milestone_type:
                # No milestone mapping - this is OK for general follow-up tasks
                logger.debug(f"No SLA milestone mapping for task {task_instance_id}")
                return result

            result["milestone_type"] = milestone_type

            # Get loan_id from task instance
            loan_id = task_data.get("loan_id")
            lead_id = task_data.get("lead_id")

            if not loan_id and not lead_id:
                result["errors"].append("Task not associated with a loan or lead")
                return result

            # Complete the SLA milestone
            milestone_result = self._complete_sla_milestone(
                loan_id=loan_id,
                lead_id=lead_id,
                milestone_type=milestone_type,
                completed_by_id=completed_by_id,
                notes=notes
            )
            result["milestone_completed"] = milestone_result.get("success", False)
            if milestone_result.get("error"):
                result["errors"].append(milestone_result["error"])

            # Update loan date field (only for loans, not leads)
            if loan_id:
                date_result = self._update_loan_date_field(
                    loan_id=loan_id,
                    milestone_type=milestone_type
                )
                result["loan_date_updated"] = date_result.get("success", False)
                result["date_field"] = date_result.get("field")
                if date_result.get("error"):
                    result["errors"].append(date_result["error"])

            logger.info(
                f"Task {task_instance_id} SLA bridge complete: "
                f"milestone={result['milestone_completed']}, date={result['loan_date_updated']}"
            )

            return result

        except Exception as e:
            logger.error(f"Error in TaskSLABridgeService.on_task_completed: {e}")
            result["errors"].append(str(e))
            return result

    def _get_task_instance(self, task_instance_id: int) -> Optional[Dict[str, Any]]:
        """Get task instance details."""
        result = self.db.execute(text("""
            SELECT
                id, workflow_instance_id, workflow_id, day_config_id,
                lead_id, loan_id, task_name, task_description, task_type,
                status, sla_milestone_type
            FROM workflow_task_instances
            WHERE id = :task_id
        """), {"task_id": task_instance_id}).fetchone()

        if not result:
            return None

        return {
            "id": result[0],
            "workflow_instance_id": result[1],
            "workflow_id": result[2],
            "day_config_id": result[3],
            "lead_id": result[4],
            "loan_id": result[5],
            "task_name": result[6],
            "task_description": result[7],
            "task_type": result[8],
            "status": result[9],
            "sla_milestone_type": result[10] if len(result) > 10 else None
        }

    def _determine_milestone_type(self, task_data: Dict[str, Any]) -> Optional[str]:
        """
        Determine the SLA milestone type from task data.

        Uses multiple strategies:
        1. Direct sla_milestone_type field if set
        2. Task type mapping
        3. Task name pattern matching
        """
        # Strategy 1: Direct mapping from sla_milestone_type field
        if task_data.get("sla_milestone_type"):
            return task_data["sla_milestone_type"]

        # Strategy 2: Map from task_type
        task_type = (task_data.get("task_type") or "").lower().strip()
        if task_type in TASK_TO_MILESTONE_MAP:
            return TASK_TO_MILESTONE_MAP[task_type]

        # Strategy 3: Pattern matching on task name
        task_name = (task_data.get("task_name") or "").lower()

        # Check for common patterns in task name
        patterns = [
            ("order title", "title_ordered"),
            ("title ordered", "title_ordered"),
            ("title received", "title_received"),
            ("order appraisal", "appraisal_ordered"),
            ("appraisal ordered", "appraisal_ordered"),
            ("appraisal received", "appraisal_received"),
            ("order insurance", "insurance_ordered"),
            ("insurance ordered", "insurance_ordered"),
            ("insurance received", "insurance_received"),
            ("send le", "le_disclosed"),
            ("le sent", "le_disclosed"),
            ("disclosure sent", "le_disclosed"),
            ("send cd", "cd_sent"),
            ("cd sent", "cd_sent"),
            ("closing disclosure", "cd_sent"),
            ("submit to uw", "submitted_to_uw"),
            ("submitted to underwriting", "submitted_to_uw"),
            ("conditions cleared", "conditions_cleared"),
            ("clear conditions", "conditions_cleared"),
            ("clear to close", "clear_to_close"),
            ("ctc", "clear_to_close"),
            ("schedule closing", "closing_scheduled"),
            ("closing scheduled", "closing_scheduled"),
            ("docs out", "closing_docs_out"),
            ("funding", "funded"),
        ]

        for pattern, milestone in patterns:
            if pattern in task_name:
                return milestone

        return None

    def _complete_sla_milestone(
        self,
        loan_id: Optional[int],
        lead_id: Optional[int],
        milestone_type: str,
        completed_by_id: Optional[int] = None,
        notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Complete an SLA milestone in the loan_milestone_history table.
        """
        try:
            # Find the active milestone for this loan/lead and type
            entity_filter = "loan_id = :loan_id" if loan_id else "lead_id = :lead_id"
            entity_id = loan_id if loan_id else lead_id

            milestone = self.db.execute(text(f"""
                SELECT id, status, started_at, target_hours
                FROM loan_milestone_history
                WHERE {entity_filter}
                AND milestone_type = :milestone_type
                AND status IN ('in_progress', 'on_track', 'at_risk', 'overdue')
                ORDER BY started_at DESC
                LIMIT 1
            """), {
                "loan_id": loan_id,
                "lead_id": lead_id,
                "milestone_type": milestone_type
            }).fetchone()

            if not milestone:
                # No active milestone found - might need to create one
                logger.info(f"No active milestone found for {milestone_type}, creating completion record")
                return self._create_completed_milestone(
                    loan_id=loan_id,
                    lead_id=lead_id,
                    milestone_type=milestone_type,
                    completed_by_id=completed_by_id,
                    notes=notes
                )

            milestone_id = milestone[0]
            started_at = milestone[2]
            target_hours = milestone[3]

            now = datetime.now(timezone.utc)

            # Calculate actual hours and variance
            actual_hours = None
            variance_hours = None
            variance_pct = None

            if started_at:
                actual_hours = (now - started_at).total_seconds() / 3600
                if target_hours:
                    variance_hours = actual_hours - target_hours
                    variance_pct = (variance_hours / target_hours) * 100 if target_hours > 0 else 0

            # Update the milestone
            self.db.execute(text("""
                UPDATE loan_milestone_history
                SET status = 'completed',
                    completed_at = :completed_at,
                    completed_by_id = :completed_by_id,
                    actual_hours = :actual_hours,
                    variance_hours = :variance_hours,
                    variance_pct = :variance_pct,
                    notes = COALESCE(notes, '') || :notes,
                    updated_at = NOW()
                WHERE id = :milestone_id
            """), {
                "milestone_id": milestone_id,
                "completed_at": now,
                "completed_by_id": completed_by_id,
                "actual_hours": actual_hours,
                "variance_hours": variance_hours,
                "variance_pct": variance_pct,
                "notes": f"\n[Task Completed]: {notes}" if notes else ""
            })

            self.db.commit()

            return {
                "success": True,
                "milestone_id": milestone_id,
                "actual_hours": actual_hours,
                "variance_hours": variance_hours
            }

        except Exception as e:
            self.db.rollback()
            logger.error(f"Error completing SLA milestone: {e}")
            return {"success": False, "error": str(e)}

    def _create_completed_milestone(
        self,
        loan_id: Optional[int],
        lead_id: Optional[int],
        milestone_type: str,
        completed_by_id: Optional[int] = None,
        notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a milestone record that is immediately marked as completed.
        Used when no active milestone exists (task was completed without prior tracking).
        """
        try:
            now = datetime.now(timezone.utc)

            # Get the SLA measure for target hours
            sla_measure = self.db.execute(text("""
                SELECT id, target_value, target_unit
                FROM sla_measures
                WHERE milestone_type = :milestone_type
                AND is_active = true
                LIMIT 1
            """), {"milestone_type": milestone_type}).fetchone()

            target_hours = None
            sla_measure_id = None
            if sla_measure:
                sla_measure_id = sla_measure[0]
                target_value = sla_measure[1]
                target_unit = sla_measure[2]
                if target_unit == 'hours':
                    target_hours = target_value
                elif target_unit == 'days':
                    target_hours = target_value * 24
                elif target_unit == 'business_days':
                    target_hours = target_value * 8  # 8 business hours per day

            # Get loan number if available
            loan_number = None
            if loan_id:
                loan_result = self.db.execute(text("""
                    SELECT loan_number FROM loans WHERE id = :loan_id
                """), {"loan_id": loan_id}).fetchone()
                if loan_result:
                    loan_number = loan_result[0]

            # Insert completed milestone
            self.db.execute(text("""
                INSERT INTO loan_milestone_history (
                    organization_id, loan_id, lead_id, loan_number,
                    sla_measure_id, milestone_type, status,
                    started_at, completed_at, completed_by_id,
                    target_hours, actual_hours, variance_hours, variance_pct,
                    notes, created_at, updated_at
                ) VALUES (
                    1, :loan_id, :lead_id, :loan_number,
                    :sla_measure_id, :milestone_type, 'completed',
                    :completed_at, :completed_at, :completed_by_id,
                    :target_hours, 0, :variance_hours, 0,
                    :notes, NOW(), NOW()
                )
            """), {
                "loan_id": loan_id,
                "lead_id": lead_id,
                "loan_number": loan_number,
                "sla_measure_id": sla_measure_id,
                "milestone_type": milestone_type,
                "completed_at": now,
                "completed_by_id": completed_by_id,
                "target_hours": target_hours,
                "variance_hours": -target_hours if target_hours else None,  # Completed instantly
                "notes": f"[Auto-created on task completion]: {notes}" if notes else "[Auto-created on task completion]"
            })

            self.db.commit()

            return {"success": True, "created": True}

        except Exception as e:
            self.db.rollback()
            logger.error(f"Error creating completed milestone: {e}")
            return {"success": False, "error": str(e)}

    def _update_loan_date_field(
        self,
        loan_id: int,
        milestone_type: str
    ) -> Dict[str, Any]:
        """
        Update the loan's Important Dates field based on milestone type.
        """
        try:
            # Get the date field for this milestone
            date_field = MILESTONE_TO_LOAN_FIELD.get(milestone_type)

            if not date_field:
                logger.debug(f"No loan date field mapping for milestone {milestone_type}")
                return {"success": False, "error": f"No date field mapping for {milestone_type}"}

            # Check if the column exists in the loans table
            column_check = self.db.execute(text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'loans'
                AND column_name = :column_name
            """), {"column_name": date_field}).fetchone()

            if not column_check:
                logger.warning(f"Column {date_field} does not exist in loans table")
                return {"success": False, "error": f"Column {date_field} not found"}

            now = datetime.now(timezone.utc)

            # Update the loan date field
            self.db.execute(text(f"""
                UPDATE loans
                SET {date_field} = :completion_date,
                    updated_at = NOW()
                WHERE id = :loan_id
            """), {
                "loan_id": loan_id,
                "completion_date": now
            })

            self.db.commit()

            logger.info(f"Updated loan {loan_id} field {date_field} to {now}")

            return {"success": True, "field": date_field, "value": now.isoformat()}

        except Exception as e:
            self.db.rollback()
            logger.error(f"Error updating loan date field: {e}")
            return {"success": False, "error": str(e)}


# ============================================================================
# Factory function
# ============================================================================

def get_task_sla_bridge_service(db: Session) -> TaskSLABridgeService:
    """Factory function to get a TaskSLABridgeService instance."""
    return TaskSLABridgeService(db)
