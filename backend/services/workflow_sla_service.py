"""
SLA Workflow Service

Core service for managing SLA-driven workflow instances.
Handles workflow lifecycle: enrollment, task generation, pausing, completion, and cancellation.

Key responsibilities:
- Enroll leads/loans into appropriate workflows based on status/stage
- Generate tasks according to workflow day configurations
- Route tasks to appropriate users based on role assignments
- Handle workflow state transitions
- Cancel sibling tasks when contact is made
- Track AI confidence for autonomous execution
"""

import logging
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional, List, Dict, Any, Tuple, Union
from sqlalchemy import and_, or_, text
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


class WorkflowSLAService:
    """
    Core service for SLA Workflow management.

    Handles the complete lifecycle of workflow instances from enrollment
    through completion, including task generation and routing.
    """

    # AI confidence threshold for auto-execution
    AI_AUTO_EXECUTE_THRESHOLD = Decimal("0.950")
    AI_REVIEW_THRESHOLD = Decimal("0.700")

    def __init__(self, db: Session):
        self.db = db
        self._load_models()

    def _load_models(self):
        """Load required models dynamically to avoid circular imports."""
        from database import Base
        from database.models import Lead, Loan, Task, User, Organization
        from workflow_config_models import create_workflow_config_models
        from models.user_onboarding import Role

        # Get workflow config models
        workflow_models = create_workflow_config_models(Base)

        self.Lead = Lead
        self.Loan = Loan
        self.Task = Task
        self.User = User
        self.Organization = Organization
        self.Role = Role
        self.WorkflowConfiguration = workflow_models['WorkflowConfiguration']
        self.WorkflowDayConfig = workflow_models['WorkflowDayConfig']
        self.WorkflowTaskInstance = workflow_models['WorkflowTaskInstance']

    # =========================================================================
    # WORKFLOW ENROLLMENT
    # =========================================================================

    def enroll_lead(
        self,
        lead_id: int,
        workflow_key: str,
        trigger_status: str = None,
        user_id: int = None
    ) -> Dict[str, Any]:
        """
        Enroll a lead into a workflow.

        Args:
            lead_id: ID of the lead to enroll
            workflow_key: Workflow key (e.g., 'prospect', 'prequal')
            trigger_status: Status that triggered enrollment
            user_id: User initiating enrollment (optional)

        Returns:
            Dict with enrollment result
        """
        try:
            # Get the lead
            lead = self.db.query(self.Lead).filter(self.Lead.id == lead_id).first()
            if not lead:
                return {"success": False, "error": f"Lead {lead_id} not found"}

            # Get organization_id from lead's owner
            org_id = None
            if lead.owner_id:
                owner = self.db.query(self.User).filter(self.User.id == lead.owner_id).first()
                if owner:
                    org_id = owner.organization_id

            # Get workflow configuration
            workflow_config = self._get_workflow_config(workflow_key, org_id)
            if not workflow_config:
                return {"success": False, "error": f"Workflow '{workflow_key}' not found"}

            # Check for existing active workflow of same type
            existing = self._get_active_workflow_instance(lead_id=lead_id, workflow_config_id=workflow_config.id)
            if existing:
                return {
                    "success": False,
                    "error": "Lead already enrolled in this workflow",
                    "existing_instance_id": existing.id
                }

            # Cancel any other active workflows for this lead
            self._cancel_other_workflows(lead_id=lead_id, new_workflow_config_id=workflow_config.id)

            # Create workflow instance
            instance = self._create_workflow_instance(
                organization_id=org_id or 1,  # Default org if not found
                workflow_config_id=workflow_config.id,
                lead_id=lead_id,
                trigger_status=trigger_status
            )

            # Update lead's current workflow reference
            lead.current_workflow_instance_id = instance.id
            self.db.commit()

            # Generate initial tasks
            tasks_created = self._generate_due_tasks(instance)

            logger.info(f"Lead {lead_id} enrolled in workflow '{workflow_key}' (instance {instance.id})")

            return {
                "success": True,
                "workflow_instance_id": instance.id,
                "workflow_key": workflow_key,
                "tasks_created": tasks_created
            }

        except IntegrityError as e:
            self.db.rollback()
            logger.error(f"Enrollment integrity error: {e.orig if hasattr(e, 'orig') else e}")
            return {"success": False, "error": "Workflow enrollment conflict"}
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"Enrollment failed: {e}")
            return {"success": False, "error": "Internal server error"}

    def enroll_loan(
        self,
        loan_id: int,
        workflow_key: str,
        trigger_status: str = None,
        user_id: int = None
    ) -> Dict[str, Any]:
        """
        Enroll a loan into a workflow.

        Args:
            loan_id: ID of the loan to enroll
            workflow_key: Workflow key (e.g., 'under_contract', 'last_mile')
            trigger_status: Status that triggered enrollment
            user_id: User initiating enrollment (optional)

        Returns:
            Dict with enrollment result
        """
        try:
            # Get the loan
            loan = self.db.query(self.Loan).filter(self.Loan.id == loan_id).first()
            if not loan:
                return {"success": False, "error": f"Loan {loan_id} not found"}

            # Get organization_id from loan officer
            org_id = None
            if loan.loan_officer_id:
                lo = self.db.query(self.User).filter(self.User.id == loan.loan_officer_id).first()
                if lo:
                    org_id = lo.organization_id

            # Get workflow configuration
            workflow_config = self._get_workflow_config(workflow_key, org_id)
            if not workflow_config:
                return {"success": False, "error": f"Workflow '{workflow_key}' not found"}

            # Check for existing active workflow of same type
            existing = self._get_active_workflow_instance(loan_id=loan_id, workflow_config_id=workflow_config.id)
            if existing:
                return {
                    "success": False,
                    "error": "Loan already enrolled in this workflow",
                    "existing_instance_id": existing.id
                }

            # Cancel any other active workflows for this loan
            self._cancel_other_workflows(loan_id=loan_id, new_workflow_config_id=workflow_config.id)

            # Create workflow instance
            instance = self._create_workflow_instance(
                organization_id=org_id or 1,
                workflow_config_id=workflow_config.id,
                loan_id=loan_id,
                trigger_status=trigger_status
            )

            # Update loan's current workflow reference
            loan.current_workflow_instance_id = instance.id
            self.db.commit()

            # Generate initial tasks
            tasks_created = self._generate_due_tasks(instance)

            logger.info(f"Loan {loan_id} enrolled in workflow '{workflow_key}' (instance {instance.id})")

            return {
                "success": True,
                "workflow_instance_id": instance.id,
                "workflow_key": workflow_key,
                "tasks_created": tasks_created
            }

        except IntegrityError as e:
            self.db.rollback()
            logger.error(f"Enrollment integrity error: {e.orig if hasattr(e, 'orig') else e}")
            return {"success": False, "error": "Workflow enrollment conflict"}
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"Enrollment failed: {e}")
            return {"success": False, "error": "Internal server error"}

    # =========================================================================
    # WORKFLOW STATE MANAGEMENT
    # =========================================================================

    def pause_workflow(
        self,
        instance_id: int,
        reason: str = None,
        user_id: int = None
    ) -> Dict[str, Any]:
        """Pause a workflow instance."""
        try:
            instance = self._get_workflow_instance(instance_id)
            if not instance:
                return {"success": False, "error": "Workflow instance not found"}

            if instance.status != 'active':
                return {"success": False, "error": f"Cannot pause workflow in '{instance.status}' status"}

            instance.status = 'paused'
            instance.paused_at = datetime.now(timezone.utc)
            self.db.commit()

            logger.info(f"Workflow instance {instance_id} paused")
            return {"success": True, "message": "Workflow paused"}

        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"Failed to pause workflow: {e}")
            return {"success": False, "error": "Internal server error"}

    def resume_workflow(
        self,
        instance_id: int,
        user_id: int = None
    ) -> Dict[str, Any]:
        """Resume a paused workflow instance."""
        try:
            instance = self._get_workflow_instance(instance_id)
            if not instance:
                return {"success": False, "error": "Workflow instance not found"}

            if instance.status != 'paused':
                return {"success": False, "error": f"Cannot resume workflow in '{instance.status}' status"}

            instance.status = 'active'
            instance.paused_at = None
            self.db.commit()

            # Generate any tasks that became due while paused
            tasks_created = self._generate_due_tasks(instance)

            logger.info(f"Workflow instance {instance_id} resumed")
            return {"success": True, "message": "Workflow resumed", "tasks_created": tasks_created}

        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"Failed to resume workflow: {e}")
            return {"success": False, "error": "Internal server error"}

    def cancel_workflow(
        self,
        instance_id: int,
        reason: str,
        user_id: int,
        superseded_by_id: int = None
    ) -> Dict[str, Any]:
        """Cancel a workflow instance."""
        try:
            instance = self._get_workflow_instance(instance_id)
            if not instance:
                return {"success": False, "error": "Workflow instance not found"}

            if instance.status in ['completed', 'cancelled']:
                return {"success": False, "error": f"Workflow already in terminal state: {instance.status}"}

            instance.status = 'cancelled'
            instance.cancelled_at = datetime.now(timezone.utc)
            instance.cancelled_by_id = user_id
            instance.cancellation_reason = reason
            instance.superseded_by_id = superseded_by_id

            # Cancel all pending/scheduled tasks
            self._cancel_pending_tasks(instance_id)

            self.db.commit()

            logger.info(f"Workflow instance {instance_id} cancelled: {reason}")
            return {"success": True, "message": "Workflow cancelled"}

        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"Failed to cancel workflow: {e}")
            return {"success": False, "error": "Internal server error"}

    def complete_workflow(
        self,
        instance_id: int
    ) -> Dict[str, Any]:
        """Mark a workflow as completed."""
        try:
            instance = self._get_workflow_instance(instance_id)
            if not instance:
                return {"success": False, "error": "Workflow instance not found"}

            if instance.status != 'active':
                return {"success": False, "error": f"Cannot complete workflow in '{instance.status}' status"}

            instance.status = 'completed'
            instance.completed_at = datetime.now(timezone.utc)

            # Cancel any remaining pending tasks
            self._cancel_pending_tasks(instance_id, reason="Workflow completed")

            self.db.commit()

            logger.info(f"Workflow instance {instance_id} completed")
            return {"success": True, "message": "Workflow completed"}

        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"Failed to complete workflow: {e}")
            return {"success": False, "error": "Internal server error"}

    # =========================================================================
    # TASK COMPLETION & SIBLING CANCELLATION
    # =========================================================================

    def complete_task(
        self,
        task_instance_id: int,
        completion_source: str,
        completed_by_id: int = None,
        outcome: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Complete a workflow task and optionally cancel siblings.

        Args:
            task_instance_id: ID of the workflow task instance
            completion_source: Source of completion ('user', 'ai', 'dialer', 'automation')
            completed_by_id: User who completed the task
            outcome: Outcome details (disposition, notes, etc.)

        Returns:
            Dict with completion result
        """
        try:
            task_instance = self.db.query(self.WorkflowTaskInstance).filter(
                self.WorkflowTaskInstance.id == task_instance_id
            ).first()

            if not task_instance:
                return {"success": False, "error": "Task instance not found"}

            if task_instance.status in ['completed', 'cancelled', 'skipped']:
                return {"success": False, "error": f"Task already in terminal state: {task_instance.status}"}

            # Update task instance
            task_instance.status = 'completed'
            task_instance.completed_at = datetime.now(timezone.utc)
            task_instance.completion_source = completion_source
            task_instance.completed_by_id = completed_by_id

            # Update linked task if exists
            if task_instance.linked_task_id:
                linked_task = self.db.query(self.Task).filter(
                    self.Task.id == task_instance.linked_task_id
                ).first()
                if linked_task:
                    linked_task.status = 'completed'
                    linked_task.completed_at = datetime.now(timezone.utc)

            # Cancel sibling tasks if contact was made
            siblings_cancelled = 0
            if task_instance.task_group_key and outcome and outcome.get('contact_made', False):
                siblings_cancelled = self._cancel_sibling_tasks(
                    task_group_key=task_instance.task_group_key,
                    exclude_task_id=task_instance_id,
                    reason="Contact made via sibling task"
                )

            # Cancel redundant SLA warning tasks for same entity
            sla_cancelled = 0
            entity_id = task_instance.lead_id or task_instance.loan_id
            entity_col = "lead_id" if task_instance.lead_id else "loan_id"
            if entity_id:
                sla_cancelled = self.db.execute(text(f"""
                    UPDATE tasks
                    SET status = 'cancelled', updated_at = NOW()
                    WHERE {entity_col} = :entity_id
                    AND sla_milestone_id IS NOT NULL
                    AND status IN ('pending')
                    AND workflow_task_instance_id IS NULL
                """), {"entity_id": entity_id}).rowcount
                if sla_cancelled:
                    logger.info(f"Cancelled {sla_cancelled} SLA warning tasks for {entity_col}={entity_id}")

            self.db.commit()

            logger.info(f"Task instance {task_instance_id} completed ({completion_source}), {siblings_cancelled} siblings cancelled")

            return {
                "success": True,
                "message": "Task completed",
                "siblings_cancelled": siblings_cancelled,
                "sla_tasks_cancelled": sla_cancelled
            }

        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"Failed to complete task: {e}")
            return {"success": False, "error": "Internal server error"}

    def skip_task(
        self,
        task_instance_id: int,
        reason: str,
        user_id: int
    ) -> Dict[str, Any]:
        """Skip a workflow task."""
        try:
            task_instance = self.db.query(self.WorkflowTaskInstance).filter(
                self.WorkflowTaskInstance.id == task_instance_id
            ).first()

            if not task_instance:
                return {"success": False, "error": "Task instance not found"}

            task_instance.status = 'skipped'
            task_instance.error_message = reason
            task_instance.completed_by_id = user_id

            # Update linked task
            if task_instance.linked_task_id:
                linked_task = self.db.query(self.Task).filter(
                    self.Task.id == task_instance.linked_task_id
                ).first()
                if linked_task:
                    linked_task.status = 'completed'
                    linked_task.description = f"{linked_task.description or ''}\n[Skipped: {reason}]"

            self.db.commit()

            return {"success": True, "message": "Task skipped"}

        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"Failed to skip task: {e}")
            return {"success": False, "error": "Internal server error"}

    # =========================================================================
    # WORKFLOW STATUS QUERIES
    # =========================================================================

    def get_workflow_status(self, instance_id: int) -> Optional[Dict[str, Any]]:
        """Get detailed status of a workflow instance."""
        instance = self._get_workflow_instance(instance_id)
        if not instance:
            return None

        # Get task counts
        task_counts = self.db.execute(text("""
            SELECT
                status,
                COUNT(*) as count
            FROM workflow_task_instances
            WHERE workflow_instance_id = :instance_id
            GROUP BY status
        """), {"instance_id": instance_id}).fetchall()

        counts_dict = {row[0]: row[1] for row in task_counts}

        # Get workflow config
        config = self.db.query(self.WorkflowConfiguration).filter(
            self.WorkflowConfiguration.id == instance.workflow_id
        ).first()

        return {
            "instance_id": instance.id,
            "workflow_key": config.workflow_key if config else None,
            "workflow_name": config.workflow_name if config else None,
            "status": instance.status,
            "started_at": instance.started_at.isoformat() if instance.started_at else None,
            "paused_at": instance.paused_at.isoformat() if instance.paused_at else None,
            "completed_at": instance.completed_at.isoformat() if instance.completed_at else None,
            "cancelled_at": instance.cancelled_at.isoformat() if instance.cancelled_at else None,
            "lead_id": instance.lead_id,
            "loan_id": instance.loan_id,
            "last_task_generated_day": instance.last_task_generated_day,
            "next_task_due_at": instance.next_task_due_at.isoformat() if instance.next_task_due_at else None,
            "task_counts": {
                "scheduled": counts_dict.get('scheduled', 0),
                "pending": counts_dict.get('pending', 0),
                "in_progress": counts_dict.get('in_progress', 0),
                "completed": counts_dict.get('completed', 0),
                "skipped": counts_dict.get('skipped', 0),
                "cancelled": counts_dict.get('cancelled', 0),
                "failed": counts_dict.get('failed', 0),
            }
        }

    def get_active_workflows_for_lead(self, lead_id: int) -> List[Dict[str, Any]]:
        """Get all active workflows for a lead."""
        results = self.db.execute(text("""
            SELECT
                wi.id,
                wi.status,
                wi.started_at,
                wc.workflow_key,
                wc.workflow_name
            FROM workflow_instances wi
            JOIN workflow_configurations wc ON wc.id = wi.workflow_configuration_id
            WHERE wi.lead_id = :lead_id
            AND wi.status IN ('active', 'paused')
            ORDER BY wi.started_at DESC
        """), {"lead_id": lead_id}).fetchall()

        return [
            {
                "instance_id": row[0],
                "status": row[1],
                "started_at": row[2].isoformat() if row[2] else None,
                "workflow_key": row[3],
                "workflow_name": row[4]
            }
            for row in results
        ]

    def get_active_workflows_for_loan(self, loan_id: int) -> List[Dict[str, Any]]:
        """Get all active workflows for a loan."""
        results = self.db.execute(text("""
            SELECT
                wi.id,
                wi.status,
                wi.started_at,
                wc.workflow_key,
                wc.workflow_name
            FROM workflow_instances wi
            JOIN workflow_configurations wc ON wc.id = wi.workflow_configuration_id
            WHERE wi.loan_id = :loan_id
            AND wi.status IN ('active', 'paused')
            ORDER BY wi.started_at DESC
        """), {"loan_id": loan_id}).fetchall()

        return [
            {
                "instance_id": row[0],
                "status": row[1],
                "started_at": row[2].isoformat() if row[2] else None,
                "workflow_key": row[3],
                "workflow_name": row[4]
            }
            for row in results
        ]

    # =========================================================================
    # PRIVATE HELPER METHODS
    # =========================================================================

    def _get_workflow_config(
        self,
        workflow_key: str,
        organization_id: int = None
    ) -> Optional[Any]:
        """
        Get workflow configuration with inheritance.

        Checks for user-specific -> org-specific -> system template.
        """
        # First try organization-specific
        if organization_id:
            config = self.db.query(self.WorkflowConfiguration).filter(
                self.WorkflowConfiguration.workflow_key == workflow_key,
                self.WorkflowConfiguration.organization_id == organization_id,
                self.WorkflowConfiguration.is_active == True
            ).first()
            if config:
                return config

        # Fall back to system template
        config = self.db.query(self.WorkflowConfiguration).filter(
            self.WorkflowConfiguration.workflow_key == workflow_key,
            self.WorkflowConfiguration.is_active == True,
            or_(
                self.WorkflowConfiguration.organization_id == None,
                self.WorkflowConfiguration.is_system_template == True
            )
        ).first()

        return config

    def _get_workflow_instance(self, instance_id: int) -> Optional[Any]:
        """Get workflow instance by ID using raw SQL (table may not be in ORM yet)."""
        result = self.db.execute(text("""
            SELECT id, organization_id, workflow_configuration_id, lead_id, loan_id,
                   status, trigger_milestone_status, trigger_milestone_entered_at,
                   started_at, paused_at, completed_at, cancelled_at,
                   cancelled_by_id, cancellation_reason, superseded_by_id,
                   last_task_generated_day, next_task_due_at
            FROM workflow_instances
            WHERE id = :id
        """), {"id": instance_id}).fetchone()

        if not result:
            return None

        # Create a simple object to hold the data
        class WorkflowInstanceData:
            pass

        instance = WorkflowInstanceData()
        instance.id = result[0]
        instance.organization_id = result[1]
        instance.workflow_configuration_id = result[2]
        instance.workflow_id = result[2]  # Alias
        instance.lead_id = result[3]
        instance.loan_id = result[4]
        instance.status = result[5]
        instance.trigger_milestone_status = result[6]
        instance.trigger_milestone_entered_at = result[7]
        instance.started_at = result[8]
        instance.paused_at = result[9]
        instance.completed_at = result[10]
        instance.cancelled_at = result[11]
        instance.cancelled_by_id = result[12]
        instance.cancellation_reason = result[13]
        instance.superseded_by_id = result[14]
        instance.last_task_generated_day = result[15]
        instance.next_task_due_at = result[16]

        return instance

    def _get_active_workflow_instance(
        self,
        lead_id: int = None,
        loan_id: int = None,
        workflow_config_id: int = None
    ) -> Optional[Any]:
        """Check for existing active workflow instance."""
        params = {"config_id": workflow_config_id}

        if lead_id:
            params["lead_id"] = lead_id
            entity_filter = "lead_id = :lead_id"
        else:
            params["loan_id"] = loan_id
            entity_filter = "loan_id = :loan_id"

        result = self.db.execute(text(f"""
            SELECT id FROM workflow_instances
            WHERE {entity_filter}
            AND workflow_configuration_id = :config_id
            AND status = 'active'
            LIMIT 1
        """), params).fetchone()

        if result:
            return self._get_workflow_instance(result[0])
        return None

    def _create_workflow_instance(
        self,
        organization_id: int,
        workflow_config_id: int,
        lead_id: int = None,
        loan_id: int = None,
        trigger_status: str = None,
        workflow_type: str = None
    ) -> Any:
        """Create a new workflow instance."""
        now = datetime.now(timezone.utc)

        # Get workflow_type from config if not provided
        if not workflow_type:
            config = self.db.execute(text("""
                SELECT workflow_key FROM workflow_configurations WHERE id = :config_id
            """), {"config_id": workflow_config_id}).fetchone()
            workflow_type = config.workflow_key if config else 'prospect'

        self.db.execute(text("""
            INSERT INTO workflow_instances (
                organization_id, workflow_configuration_id,
                workflow_type,
                lead_id, loan_id, status,
                trigger_milestone_status, trigger_milestone_entered_at,
                started_at, last_task_generated_day,
                created_at, updated_at
            ) VALUES (
                :org_id, :config_id,
                :workflow_type,
                :lead_id, :loan_id, 'active',
                :trigger_status, :trigger_time,
                :started_at, -1,
                :created_at, :updated_at
            )
        """), {
            "org_id": organization_id,
            "config_id": workflow_config_id,
            "workflow_type": workflow_type,
            "lead_id": lead_id,
            "loan_id": loan_id,
            "trigger_status": trigger_status,
            "trigger_time": now,
            "started_at": now,
            "created_at": now,
            "updated_at": now
        })
        self.db.flush()

        # Get the created instance
        if lead_id:
            result = self.db.execute(text("""
                SELECT id FROM workflow_instances
                WHERE lead_id = :lead_id
                AND workflow_configuration_id = :config_id
                ORDER BY id DESC LIMIT 1
            """), {"lead_id": lead_id, "config_id": workflow_config_id}).fetchone()
        else:
            result = self.db.execute(text("""
                SELECT id FROM workflow_instances
                WHERE loan_id = :loan_id
                AND workflow_configuration_id = :config_id
                ORDER BY id DESC LIMIT 1
            """), {"loan_id": loan_id, "config_id": workflow_config_id}).fetchone()

        return self._get_workflow_instance(result[0])

    def _cancel_other_workflows(
        self,
        lead_id: int = None,
        loan_id: int = None,
        new_workflow_config_id: int = None
    ):
        """Cancel other active workflows for an entity."""
        params = {"new_config_id": new_workflow_config_id}

        if lead_id:
            params["lead_id"] = lead_id
            entity_filter = "lead_id = :lead_id"
        else:
            params["loan_id"] = loan_id
            entity_filter = "loan_id = :loan_id"

        self.db.execute(text(f"""
            UPDATE workflow_instances
            SET status = 'cancelled',
                cancelled_at = NOW(),
                cancellation_reason = 'Superseded by new workflow enrollment'
            WHERE {entity_filter}
            AND status = 'active'
            AND workflow_configuration_id != :new_config_id
        """), params)

    def _cancel_pending_tasks(self, instance_id: int, reason: str = "Workflow cancelled"):
        """Cancel all pending/scheduled tasks for a workflow instance."""
        self.db.execute(text("""
            UPDATE workflow_task_instances
            SET status = 'cancelled',
                error_message = :reason,
                updated_at = NOW()
            WHERE workflow_instance_id = :instance_id
            AND status IN ('scheduled', 'pending', 'in_progress')
        """), {"instance_id": instance_id, "reason": reason})

        # Also cancel linked tasks
        self.db.execute(text("""
            UPDATE tasks
            SET status = 'completed',
                description = COALESCE(description, '') || E'\n[Cancelled: ' || :reason || ']'
            WHERE workflow_task_instance_id IN (
                SELECT id FROM workflow_task_instances
                WHERE workflow_instance_id = :instance_id
            )
            AND status NOT IN ('completed')
        """), {"instance_id": instance_id, "reason": reason})

    def _cancel_sibling_tasks(
        self,
        task_group_key: str,
        exclude_task_id: int,
        reason: str
    ) -> int:
        """Cancel sibling tasks in the same group."""
        result = self.db.execute(text("""
            UPDATE workflow_task_instances
            SET status = 'cancelled',
                error_message = :reason,
                updated_at = NOW()
            WHERE task_group_key = :group_key
            AND id != :exclude_id
            AND status IN ('scheduled', 'pending', 'in_progress')
        """), {
            "group_key": task_group_key,
            "exclude_id": exclude_task_id,
            "reason": reason
        })

        return result.rowcount

    def _generate_due_tasks(self, instance) -> int:
        """
        Generate tasks that are due based on workflow configuration.

        This is called during enrollment and by the scheduler.
        Returns the number of tasks created.
        """
        try:
            # Get instance data
            if hasattr(instance, 'id'):
                inst_id = instance.id
                config_id = instance.workflow_configuration_id
                lead_id = getattr(instance, 'lead_id', None)
                loan_id = getattr(instance, 'loan_id', None)
                org_id = getattr(instance, 'organization_id', 1)
                trigger_time = getattr(instance, 'trigger_milestone_entered_at', None) or getattr(instance, 'started_at', None)
                last_generated = getattr(instance, 'last_task_generated_day', -1) or -1
            elif isinstance(instance, dict):
                inst_id = instance.get('id')
                config_id = instance.get('workflow_configuration_id')
                lead_id = instance.get('lead_id')
                loan_id = instance.get('loan_id')
                org_id = instance.get('organization_id', 1)
                trigger_time = instance.get('trigger_milestone_entered_at') or instance.get('started_at')
                last_generated = instance.get('last_task_generated_day', -1) or -1
            else:
                logger.warning("Cannot generate tasks: invalid instance type")
                return 0

            if not inst_id or not config_id:
                logger.warning(f"Cannot generate tasks: missing instance_id={inst_id} or config_id={config_id}")
                return 0

            # Calculate days elapsed
            if trigger_time:
                now = datetime.now(timezone.utc)
                if trigger_time.tzinfo is None:
                    trigger_time = trigger_time.replace(tzinfo=timezone.utc)
                days_elapsed = (now - trigger_time).days
            else:
                days_elapsed = 0

            logger.info(f"Generating tasks for instance {inst_id}: days_elapsed={days_elapsed}, last_generated={last_generated}")

            # Get eligible day configs
            day_configs = self.db.execute(text("""
                SELECT id, day_value, day_label,
                       phone_enabled, email_enabled, text_enabled,
                       task_description
                FROM workflow_day_configs
                WHERE workflow_id = :config_id
                  AND is_active = true
                  AND day_value <= :days_elapsed
                  AND day_value > :last_generated
                ORDER BY day_value
            """), {
                "config_id": config_id,
                "days_elapsed": days_elapsed,
                "last_generated": last_generated
            }).fetchall()

            tasks_created = 0
            max_day_generated = last_generated

            for dc in day_configs:
                dc_id = dc[0]
                day_value = dc[1]
                day_label = dc[2]
                phone = dc[3]
                email = dc[4]
                text_enabled = dc[5]
                description = dc[6] or day_label

                task_types = []
                if phone: task_types.append("phone")
                if email: task_types.append("email")
                if text_enabled: task_types.append("text")

                for task_type in task_types:
                    # Create task instance
                    self.db.execute(text("""
                        INSERT INTO workflow_task_instances (
                            workflow_instance_id, workflow_id, day_config_id,
                            organization_id, task_type, task_name, task_description,
                            day_number, status, lead_id, loan_id,
                            scheduled_date, due_date, created_at, updated_at
                        ) VALUES (
                            :instance_id, :workflow_id, :day_config_id,
                            :org_id, :task_type, :task_name, :task_description,
                            :day_number, 'pending', :lead_id, :loan_id,
                            NOW(), NOW() + INTERVAL '1 day', NOW(), NOW()
                        )
                    """), {
                        "instance_id": inst_id,
                        "workflow_id": config_id,
                        "day_config_id": dc_id,
                        "org_id": org_id,
                        "task_type": task_type,
                        "task_name": f"{day_label} - {task_type.title()}",
                        "task_description": description,
                        "day_number": day_value,
                        "lead_id": lead_id,
                        "loan_id": loan_id
                    })
                    tasks_created += 1

                if day_value > max_day_generated:
                    max_day_generated = day_value

            # Update last_task_generated_day
            if max_day_generated > last_generated:
                self.db.execute(text("""
                    UPDATE workflow_instances
                    SET last_task_generated_day = :day, updated_at = NOW()
                    WHERE id = :id
                """), {"day": max_day_generated, "id": inst_id})

            # Commit the tasks
            self.db.commit()

            logger.info(f"Generated {tasks_created} tasks for instance {inst_id}")
            return tasks_created

        except SQLAlchemyError as e:
            self.db.rollback()
            import traceback
            logger.error(f"Error generating tasks: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return 0


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def get_workflow_service(db: Session) -> WorkflowSLAService:
    """Factory function to get a WorkflowSLAService instance."""
    return WorkflowSLAService(db)
