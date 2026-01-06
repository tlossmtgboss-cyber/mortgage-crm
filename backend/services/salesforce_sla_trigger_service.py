"""
Salesforce-to-SLA Trigger Service

Connects Salesforce date field syncs to SLA workflow enrollment and task generation.
When Salesforce updates key milestone dates (closing date, lock date, etc.), this service
automatically enrolls loans/leads into the appropriate SLA workflows.

Key Triggers:
- Contract date → under_contract workflow
- Lock date → rate_lock workflow
- Clear to close date → closing workflow
- Application date → prequal workflow
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)


# Salesforce field to SLA workflow mapping
# Format: "salesforce_field" -> (workflow_key, entity_type, days_before_due)
SALESFORCE_SLA_TRIGGERS = {
    # Date fields from Salesforce sync
    "contract_received_date": {
        "workflow_key": "under_contract",
        "entity_type": "loan",
        "trigger_name": "Contract Received",
        "sla_type": "countdown",  # Tasks generated counting down to this date
    },
    "closing_date": {
        "workflow_key": "closing",
        "entity_type": "loan",
        "trigger_name": "Closing Date",
        "sla_type": "countdown",
        "days_before_alerts": [14, 7, 3, 1],  # Send task alerts at these days before
    },
    "lock_date": {
        "workflow_key": "rate_lock",
        "entity_type": "loan",
        "trigger_name": "Rate Lock",
        "sla_type": "countdown",
    },
    "lock_expiration_date": {
        "workflow_key": "lock_expiration",
        "entity_type": "loan",
        "trigger_name": "Lock Expiration",
        "sla_type": "countdown",
        "days_before_alerts": [7, 3, 1],  # Urgency for lock expiration
    },
    "application_date": {
        "workflow_key": "prequal",
        "entity_type": "loan",
        "trigger_name": "Application Received",
        "sla_type": "elapsed",  # Tasks generated based on days since date
    },
    "disclosure_sent_date": {
        "workflow_key": "disclosure_sent",
        "entity_type": "loan",
        "trigger_name": "Disclosure Sent",
        "sla_type": "elapsed",
    },
}

# Status-based workflow triggers
SALESFORCE_STATUS_TRIGGERS = {
    "In Processing": "under_contract",
    "In Underwriting": "underwriting",
    "Approved": "approved",
    "Clear to Close": "closing",
    "Docs Out": "closing",
    "Funded": None,  # Completes workflow, no new enrollment
    "Cancelled": None,
    "Denied": None,
}


class SalesforceSLATriggerService:
    """
    Service that triggers SLA workflows based on Salesforce data changes.

    Called after each Salesforce sync to:
    1. Detect changed date fields
    2. Enroll in appropriate SLA workflows
    3. Update existing workflow dates if changed
    """

    def __init__(self, db: Session):
        self.db = db
        self._sla_service = None

    @property
    def sla_service(self):
        """Lazy load SLA service to avoid circular imports."""
        if self._sla_service is None:
            from services.workflow_sla_service import WorkflowSLAService
            self._sla_service = WorkflowSLAService(self.db)
        return self._sla_service

    def process_sync_result(
        self,
        entity_type: str,  # "lead" or "loan"
        entity_id: int,
        old_data: Dict[str, Any],
        new_data: Dict[str, Any],
        sync_source: str = "salesforce"
    ) -> Dict[str, Any]:
        """
        Process a Salesforce sync result and trigger appropriate SLA workflows.

        Args:
            entity_type: "lead" or "loan"
            entity_id: ID of the lead or loan
            old_data: Data before sync (for comparison)
            new_data: Data after sync
            sync_source: Source of sync (salesforce, webhook, etc.)

        Returns:
            Dict with triggered workflows and any errors
        """
        results = {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "workflows_triggered": [],
            "workflows_updated": [],
            "errors": []
        }

        try:
            # Check date field changes
            date_triggers = self._check_date_triggers(
                entity_type, entity_id, old_data, new_data
            )

            for trigger in date_triggers:
                workflow_result = self._process_date_trigger(
                    entity_type, entity_id, trigger, new_data
                )
                if workflow_result.get("success"):
                    results["workflows_triggered"].append(workflow_result)
                elif workflow_result.get("updated"):
                    results["workflows_updated"].append(workflow_result)
                else:
                    results["errors"].append(workflow_result)

            # Check status changes
            if "status" in new_data and old_data.get("status") != new_data.get("status"):
                status_result = self._process_status_change(
                    entity_type, entity_id,
                    old_data.get("status"),
                    new_data.get("status")
                )
                if status_result:
                    if status_result.get("success"):
                        results["workflows_triggered"].append(status_result)
                    else:
                        results["errors"].append(status_result)

            logger.info(
                f"Salesforce SLA triggers processed for {entity_type} {entity_id}: "
                f"{len(results['workflows_triggered'])} triggered, "
                f"{len(results['workflows_updated'])} updated"
            )

        except Exception as e:
            logger.error(f"Error processing Salesforce SLA triggers: {e}")
            results["errors"].append({"error": str(e)})

        return results

    def _check_date_triggers(
        self,
        entity_type: str,
        entity_id: int,
        old_data: Dict[str, Any],
        new_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Check for date field changes that should trigger SLA workflows.

        Returns list of triggers to process.
        """
        triggers = []

        for field_name, config in SALESFORCE_SLA_TRIGGERS.items():
            # Skip if entity type doesn't match
            if config["entity_type"] != entity_type:
                continue

            old_value = old_data.get(field_name)
            new_value = new_data.get(field_name)

            # Check if date was added or changed
            if new_value and (not old_value or old_value != new_value):
                triggers.append({
                    "field_name": field_name,
                    "old_value": old_value,
                    "new_value": new_value,
                    "config": config
                })

        return triggers

    def _process_date_trigger(
        self,
        entity_type: str,
        entity_id: int,
        trigger: Dict[str, Any],
        entity_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Process a date field trigger and enroll in SLA workflow.
        """
        config = trigger["config"]
        workflow_key = config["workflow_key"]

        try:
            # Check if already enrolled in this workflow
            existing = self._get_active_workflow(entity_type, entity_id, workflow_key)

            if existing:
                # Update the trigger date if it changed
                result = self._update_workflow_trigger_date(
                    existing["instance_id"],
                    trigger["new_value"]
                )
                return {
                    "success": False,
                    "updated": True,
                    "workflow_key": workflow_key,
                    "instance_id": existing["instance_id"],
                    "message": f"Updated trigger date for existing workflow"
                }

            # Enroll in the SLA workflow
            if entity_type == "loan":
                result = self.sla_service.enroll_loan(
                    loan_id=entity_id,
                    workflow_key=workflow_key,
                    trigger_status=config["trigger_name"]
                )
            else:
                result = self.sla_service.enroll_lead(
                    lead_id=entity_id,
                    workflow_key=workflow_key,
                    trigger_status=config["trigger_name"]
                )

            if result.get("success"):
                logger.info(
                    f"Enrolled {entity_type} {entity_id} in SLA workflow '{workflow_key}' "
                    f"triggered by {trigger['field_name']}"
                )

                # If it's a countdown workflow, generate countdown tasks
                if config.get("sla_type") == "countdown":
                    self._generate_countdown_tasks(
                        result["workflow_instance_id"],
                        trigger["new_value"],
                        config.get("days_before_alerts", [14, 7, 3, 1])
                    )

                return {
                    "success": True,
                    "workflow_key": workflow_key,
                    "instance_id": result.get("workflow_instance_id"),
                    "trigger_field": trigger["field_name"],
                    "trigger_date": str(trigger["new_value"])
                }
            else:
                return {
                    "success": False,
                    "workflow_key": workflow_key,
                    "error": result.get("error", "Unknown error")
                }

        except Exception as e:
            logger.error(f"Error processing date trigger: {e}")
            return {
                "success": False,
                "workflow_key": workflow_key,
                "error": str(e)
            }

    def _process_status_change(
        self,
        entity_type: str,
        entity_id: int,
        old_status: str,
        new_status: str
    ) -> Optional[Dict[str, Any]]:
        """
        Process a loan status change and trigger appropriate workflow.
        """
        workflow_key = SALESFORCE_STATUS_TRIGGERS.get(new_status)

        if workflow_key is None:
            # Terminal status - complete any active workflows
            if new_status in ["Funded", "Cancelled", "Denied"]:
                self._complete_active_workflows(entity_type, entity_id, new_status)
            return None

        try:
            # Check if already enrolled
            existing = self._get_active_workflow(entity_type, entity_id, workflow_key)
            if existing:
                return None  # Already in this workflow

            # Enroll in the workflow
            if entity_type == "loan":
                result = self.sla_service.enroll_loan(
                    loan_id=entity_id,
                    workflow_key=workflow_key,
                    trigger_status=new_status
                )
            else:
                result = self.sla_service.enroll_lead(
                    lead_id=entity_id,
                    workflow_key=workflow_key,
                    trigger_status=new_status
                )

            if result.get("success"):
                logger.info(
                    f"Enrolled {entity_type} {entity_id} in SLA workflow '{workflow_key}' "
                    f"due to status change: {old_status} -> {new_status}"
                )
                return {
                    "success": True,
                    "workflow_key": workflow_key,
                    "instance_id": result.get("workflow_instance_id"),
                    "trigger_status": new_status
                }
            else:
                return {
                    "success": False,
                    "workflow_key": workflow_key,
                    "error": result.get("error")
                }

        except Exception as e:
            logger.error(f"Error processing status change: {e}")
            return {
                "success": False,
                "workflow_key": workflow_key,
                "error": str(e)
            }

    def _get_active_workflow(
        self,
        entity_type: str,
        entity_id: int,
        workflow_key: str
    ) -> Optional[Dict[str, Any]]:
        """Check if entity is already enrolled in a specific workflow."""
        entity_filter = "lead_id" if entity_type == "lead" else "loan_id"

        result = self.db.execute(text(f"""
            SELECT wi.id, wi.status, wc.workflow_key
            FROM workflow_instances wi
            JOIN workflow_configurations wc ON wc.id = wi.workflow_configuration_id
            WHERE wi.{entity_filter} = :entity_id
            AND wc.workflow_key = :workflow_key
            AND wi.status = 'active'
            LIMIT 1
        """), {
            "entity_id": entity_id,
            "workflow_key": workflow_key
        }).fetchone()

        if result:
            return {
                "instance_id": result[0],
                "status": result[1],
                "workflow_key": result[2]
            }
        return None

    def _update_workflow_trigger_date(
        self,
        instance_id: int,
        new_date: Any
    ) -> bool:
        """Update the trigger date for an existing workflow instance."""
        try:
            self.db.execute(text("""
                UPDATE workflow_instances
                SET trigger_milestone_entered_at = :new_date,
                    updated_at = NOW()
                WHERE id = :instance_id
            """), {
                "instance_id": instance_id,
                "new_date": new_date
            })
            self.db.commit()
            return True
        except Exception as e:
            logger.error(f"Error updating workflow trigger date: {e}")
            self.db.rollback()
            return False

    def _complete_active_workflows(
        self,
        entity_type: str,
        entity_id: int,
        terminal_status: str
    ):
        """Complete all active workflows when entity reaches terminal status."""
        entity_filter = "lead_id" if entity_type == "lead" else "loan_id"

        try:
            self.db.execute(text(f"""
                UPDATE workflow_instances
                SET status = CASE
                    WHEN :status = 'Funded' THEN 'completed'
                    ELSE 'cancelled'
                END,
                completed_at = CASE
                    WHEN :status = 'Funded' THEN NOW()
                    ELSE completed_at
                END,
                cancelled_at = CASE
                    WHEN :status != 'Funded' THEN NOW()
                    ELSE cancelled_at
                END,
                cancellation_reason = CASE
                    WHEN :status != 'Funded' THEN 'Loan status: ' || :status
                    ELSE cancellation_reason
                END,
                updated_at = NOW()
                WHERE {entity_filter} = :entity_id
                AND status = 'active'
            """), {
                "entity_id": entity_id,
                "status": terminal_status
            })
            self.db.commit()

            logger.info(
                f"Completed active workflows for {entity_type} {entity_id} "
                f"due to terminal status: {terminal_status}"
            )
        except Exception as e:
            logger.error(f"Error completing workflows: {e}")
            self.db.rollback()

    def _generate_countdown_tasks(
        self,
        workflow_instance_id: int,
        target_date: Any,
        days_before_alerts: List[int]
    ):
        """
        Generate countdown tasks for a target date.

        Creates tasks at specified intervals before the target date.
        """
        try:
            # Parse target date
            if isinstance(target_date, str):
                target_date = datetime.fromisoformat(target_date.replace('Z', '+00:00'))
            elif not isinstance(target_date, datetime):
                target_date = datetime.combine(target_date, datetime.min.time())

            if target_date.tzinfo is None:
                target_date = target_date.replace(tzinfo=timezone.utc)

            now = datetime.now(timezone.utc)

            for days_before in days_before_alerts:
                task_due = target_date - timedelta(days=days_before)

                # Skip if already past
                if task_due < now:
                    continue

                # Create countdown task
                self.db.execute(text("""
                    INSERT INTO workflow_task_instances (
                        workflow_instance_id,
                        task_type, task_name, task_description,
                        status, due_date, scheduled_date,
                        created_at, updated_at
                    ) VALUES (
                        :instance_id,
                        'countdown_reminder',
                        :task_name,
                        :task_description,
                        'scheduled',
                        :due_date,
                        :scheduled_date,
                        NOW(), NOW()
                    )
                """), {
                    "instance_id": workflow_instance_id,
                    "task_name": f"{days_before} Days Before - Countdown Task",
                    "task_description": f"Action required: {days_before} days remaining until target date",
                    "due_date": task_due,
                    "scheduled_date": task_due
                })

            self.db.commit()
            logger.info(f"Generated countdown tasks for workflow instance {workflow_instance_id}")

        except Exception as e:
            logger.error(f"Error generating countdown tasks: {e}")
            self.db.rollback()


def get_salesforce_sla_trigger_service(db: Session) -> SalesforceSLATriggerService:
    """Factory function to get a SalesforceSLATriggerService instance."""
    return SalesforceSLATriggerService(db)
