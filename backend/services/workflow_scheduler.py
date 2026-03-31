"""
Workflow Scheduler Service

Handles scheduled workflow operations:
- Periodic task generation for active workflows
- Status change detection and workflow enrollment
- Overdue task escalation (using business hours, not calendar time)
- Workflow completion checks

Can be run as a background task or triggered via API/cron.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from sqlalchemy import text
from sqlalchemy.orm import Session
import asyncio
from sqlalchemy.exc import SQLAlchemyError

from services.workflow_constants import (
    LEAD_STATUS_WORKFLOW_MAP,
    LEAD_SKIP_STAGES,
    LOAN_STAGE_WORKFLOW_MAP,
    LOAN_SKIP_STAGES,
    ESCALATION_CHAIN,
)

logger = logging.getLogger(__name__)


# =============================================================================
# BUSINESS HOURS HELPER (SLA-008)
# =============================================================================

def _business_hours_elapsed(start_dt: datetime, end_dt: datetime) -> float:
    """
    Calculate business hours elapsed between two datetimes.

    Business hours: Monday-Friday, 8:00 AM - 6:00 PM (10 hours/day).
    Weekends (Saturday/Sunday) are skipped entirely.

    Returns the number of business hours as a float.
    """
    if end_dt <= start_dt:
        return 0.0

    BIZ_START_HOUR = 8
    BIZ_END_HOUR = 18
    HOURS_PER_DAY = BIZ_END_HOUR - BIZ_START_HOUR  # 10

    total_hours = 0.0
    current = start_dt

    while current < end_dt:
        weekday = current.weekday()  # 0=Mon, 6=Sun

        # Skip weekends
        if weekday >= 5:
            # Advance to next Monday at BIZ_START_HOUR
            days_to_monday = 7 - weekday
            current = current.replace(
                hour=BIZ_START_HOUR, minute=0, second=0, microsecond=0
            ) + timedelta(days=days_to_monday)
            continue

        # Clamp current time to business hours
        day_start = current.replace(
            hour=BIZ_START_HOUR, minute=0, second=0, microsecond=0
        )
        day_end = current.replace(
            hour=BIZ_END_HOUR, minute=0, second=0, microsecond=0
        )

        # If current is before business hours, advance to start
        if current < day_start:
            current = day_start
            continue

        # If current is after business hours, advance to next business day
        if current >= day_end:
            next_day = current + timedelta(days=1)
            current = next_day.replace(
                hour=BIZ_START_HOUR, minute=0, second=0, microsecond=0
            )
            continue

        # We're within business hours on a weekday
        # Calculate hours until end of business day or end_dt, whichever is sooner
        effective_end = min(end_dt, day_end)

        # If effective_end is on a weekend or before current, move on
        if effective_end <= current:
            next_day = current + timedelta(days=1)
            current = next_day.replace(
                hour=BIZ_START_HOUR, minute=0, second=0, microsecond=0
            )
            continue

        hours_this_segment = (effective_end - current).total_seconds() / 3600.0
        total_hours += hours_this_segment

        # Move to after this segment
        if effective_end >= day_end:
            next_day = current + timedelta(days=1)
            current = next_day.replace(
                hour=BIZ_START_HOUR, minute=0, second=0, microsecond=0
            )
        else:
            current = effective_end

    return total_hours


class WorkflowScheduler:
    """
    Scheduler for workflow operations.

    Handles periodic processing of workflow tasks and status monitoring.
    """

    # Default intervals (in seconds)
    TASK_GENERATION_INTERVAL = 300  # 5 minutes
    STATUS_CHECK_INTERVAL = 60  # 1 minute
    ESCALATION_INTERVAL = 3600  # 1 hour

    # Imported from workflow_constants (canonical source of truth)
    ESCALATION_CHAIN = ESCALATION_CHAIN

    def __init__(self, db: Session):
        self.db = db
        self._running = False
        self._task_generator = None
        self._workflow_service = None

    def _get_task_generator(self):
        """Lazy load task generator."""
        if not self._task_generator:
            from services.workflow_task_generator import TaskGeneratorService
            self._task_generator = TaskGeneratorService(self.db)
        return self._task_generator

    def _get_workflow_service(self):
        """Lazy load workflow service."""
        if not self._workflow_service:
            from services.workflow_sla_service import WorkflowSLAService
            self._workflow_service = WorkflowSLAService(self.db)
        return self._workflow_service

    # =========================================================================
    # TASK GENERATION
    # =========================================================================

    def generate_due_tasks(self) -> Dict[str, Any]:
        """
        Generate tasks for all active workflows that have due tasks.

        This is the main scheduled operation that should run periodically.
        """
        try:
            generator = self._get_task_generator()
            return generator.generate_scheduled_tasks()

        except Exception as e:
            logger.error(f"Task generation failed: {e}")
            return {"success": False, "error": "Internal server error"}

    def generate_tasks_for_workflow(self, instance_id: int) -> Dict[str, Any]:
        """Generate tasks for a specific workflow instance."""
        try:
            generator = self._get_task_generator()
            return generator.generate_tasks_for_instance(instance_id)

        except Exception as e:
            logger.error(f"Task generation for instance {instance_id} failed: {e}")
            return {"success": False, "error": "Internal server error"}

    # =========================================================================
    # STATUS CHANGE DETECTION
    # =========================================================================

    def process_status_changes(self) -> Dict[str, Any]:
        """
        Detect and process status/stage changes that should trigger workflow enrollment.

        Checks leads and loans for status changes and enrolls them in appropriate workflows.
        """
        try:
            workflow_service = self._get_workflow_service()
            results = {
                "leads_processed": 0,
                "loans_processed": 0,
                "workflows_enrolled": 0,
                "errors": []
            }

            # Process lead status changes
            lead_results = self._process_lead_status_changes(workflow_service)
            results["leads_processed"] = lead_results.get("processed", 0)
            results["workflows_enrolled"] += lead_results.get("enrolled", 0)
            results["errors"].extend(lead_results.get("errors", []))

            # Process loan status changes
            loan_results = self._process_loan_status_changes(workflow_service)
            results["loans_processed"] = loan_results.get("processed", 0)
            results["workflows_enrolled"] += loan_results.get("enrolled", 0)
            results["errors"].extend(loan_results.get("errors", []))

            logger.info(f"Status change processing: {results['workflows_enrolled']} workflows enrolled")

            return {"success": True, **results}

        except Exception as e:
            logger.error(f"Status change processing failed: {e}")
            return {"success": False, "error": "Internal server error"}

    def _process_lead_status_changes(self, workflow_service) -> Dict[str, Any]:
        """Process lead status changes for workflow enrollment."""
        results = {"processed": 0, "enrolled": 0, "errors": []}

        # Imported from workflow_constants (canonical source of truth)
        status_workflow_map = LEAD_STATUS_WORKFLOW_MAP
        skip_stages = LEAD_SKIP_STAGES

        # Find leads that changed status recently and don't have an active workflow
        # We use stage_changed_at if available, otherwise fall back to updated_at
        # Note: stage is an enum, source is the lead source string
        leads = self.db.execute(text("""
            SELECT l.id, l.stage::text, l.source
            FROM leads l
            LEFT JOIN workflow_instances wi ON wi.lead_id = l.id AND wi.status = 'active'
            WHERE wi.id IS NULL
            AND l.stage IS NOT NULL
            AND (
                l.stage_changed_at >= NOW() - INTERVAL '1 hour'
                OR (l.stage_changed_at IS NULL AND l.updated_at >= NOW() - INTERVAL '1 hour')
            )
            LIMIT 100
        """)).fetchall()

        for lead_id, stage, source in leads:
            results["processed"] += 1

            # Skip stages that should not trigger workflow enrollment
            if stage in skip_stages:
                continue

            # Determine workflow
            workflow_key = status_workflow_map.get(stage)

            # Special case: purchased leads use lead_purchase workflow
            # source contains lead source info like "purchased", "organic", etc.
            if source and 'purchased' in source.lower() and stage in ['New', 'Attempted Contact', 'Prospect']:
                workflow_key = 'lead_purchase'

            if not workflow_key:
                continue

            # Enroll in workflow
            enroll_result = workflow_service.enroll_lead(
                lead_id=lead_id,
                workflow_key=workflow_key,
                trigger_status=stage
            )

            if enroll_result.get("success"):
                results["enrolled"] += 1
            else:
                error = enroll_result.get("error", "Unknown error")
                if "already enrolled" not in error.lower():
                    results["errors"].append({"lead_id": lead_id, "error": error})

        return results

    def _process_loan_status_changes(self, workflow_service) -> Dict[str, Any]:
        """Process loan status changes for workflow enrollment."""
        results = {"processed": 0, "enrolled": 0, "errors": []}

        # Imported from workflow_constants (canonical source of truth)
        stage_workflow_map = LOAN_STAGE_WORKFLOW_MAP
        loan_skip_stages = LOAN_SKIP_STAGES

        # Find loans that changed stage recently
        loans = self.db.execute(text("""
            SELECT l.id, l.stage::text
            FROM loans l
            LEFT JOIN workflow_instances wi ON wi.loan_id = l.id AND wi.status = 'active'
            WHERE wi.id IS NULL
            AND l.stage IS NOT NULL
            AND l.stage_changed_at >= NOW() - INTERVAL '1 hour'
            LIMIT 100
        """)).fetchall()

        for loan_id, stage in loans:
            results["processed"] += 1

            # Skip stages that should not trigger workflow enrollment
            if stage in loan_skip_stages:
                continue

            workflow_key = stage_workflow_map.get(stage)
            if not workflow_key:
                continue

            # Enroll in workflow
            enroll_result = workflow_service.enroll_loan(
                loan_id=loan_id,
                workflow_key=workflow_key,
                trigger_status=stage
            )

            if enroll_result.get("success"):
                results["enrolled"] += 1
            else:
                error = enroll_result.get("error", "Unknown error")
                if "already enrolled" not in error.lower():
                    results["errors"].append({"loan_id": loan_id, "error": error})

        return results

    # =========================================================================
    # OVERDUE TASK ESCALATION
    # =========================================================================

    def escalate_overdue_tasks(self) -> Dict[str, Any]:
        """
        Find and escalate overdue workflow tasks using multi-level escalation.

        SLA-002: Uses ESCALATION_CHAIN for incremental escalation:
        - Level 1 (24h): Notify assignee
        - Level 2 (48h): Notify manager + reassign
        - Level 3 (72h): Notify branch manager + flag critical
        """
        try:
            # Find overdue tasks with their current escalation level
            overdue = self.db.execute(text("""
                SELECT
                    wti.id,
                    wti.task_name,
                    wti.due_date,
                    wti.assigned_user_id,
                    wti.lead_id,
                    wti.loan_id,
                    wi.organization_id,
                    COALESCE(wti.escalation_level, 0) as current_level,
                    EXTRACT(EPOCH FROM (NOW() - wti.due_date)) / 3600 as hours_overdue
                FROM workflow_task_instances wti
                JOIN workflow_instances wi ON wi.id = wti.workflow_instance_id
                WHERE wti.status IN ('scheduled', 'pending')
                AND wti.due_date < NOW()
                AND wi.status = 'active'
                LIMIT 100
            """)).fetchall()

            escalated = 0
            now = datetime.now(timezone.utc)
            for task in overdue:
                task_id = task[0]
                task_name = task[1]
                due_date = task[2]
                user_id = task[3]
                lead_id = task[4]
                loan_id = task[5]
                org_id = task[6]
                current_level = task[7] or 0
                # SLA-008: Use business hours instead of raw calendar hours
                biz_hours_overdue = _business_hours_elapsed(due_date, now) if due_date else 0

                # Determine target escalation level based on business hours overdue
                target_level = 0
                for level, config in sorted(self.ESCALATION_CHAIN.items()):
                    if biz_hours_overdue >= config["hours_overdue"]:
                        target_level = level

                # Skip if already escalated to this level or no escalation needed
                if target_level <= current_level or target_level == 0:
                    continue

                chain_config = self.ESCALATION_CHAIN[target_level]
                severity = "critical" if target_level >= 3 else "high" if target_level >= 2 else "medium"

                # Update task escalation level and health status
                self.db.execute(text("""
                    UPDATE workflow_task_instances
                    SET health_status = :health,
                        error_message = :msg,
                        escalation_level = :level,
                        updated_at = NOW()
                    WHERE id = :id
                """), {
                    "id": task_id,
                    "health": "broken" if target_level >= 2 else "healthy",
                    "msg": f"Escalation level {target_level}: {chain_config['action']} ({biz_hours_overdue:.0f} biz hours overdue)",
                    "level": target_level,
                })

                # Create alert record
                try:
                    self.db.execute(text("""
                        INSERT INTO workflow_task_alerts (
                            task_instance_id, alert_type, severity, message, created_at
                        ) VALUES (
                            :task_id, :alert_type, :severity, :message, NOW()
                        )
                    """), {
                        "task_id": task_id,
                        "alert_type": f"escalation_level_{target_level}",
                        "severity": severity,
                        "message": f"Task overdue {biz_hours_overdue:.0f} biz hours - escalated to {chain_config['target']}",
                    })
                except Exception as e:
                    logger.exception(f"Failed to insert escalation alert record: {e}")

                # Send notification to appropriate target
                self._send_escalation_notification(
                    task_id=task_id,
                    task_name=task_name,
                    target_level=target_level,
                    chain_config=chain_config,
                    user_id=user_id,
                    org_id=org_id,
                    hours_overdue=biz_hours_overdue,
                )

                escalated += 1

            self.db.commit()

            logger.info(f"Escalated {escalated} overdue tasks (multi-level)")

            return {
                "success": True,
                "escalated_count": escalated
            }

        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"Task escalation failed: {e}")
            return {"success": False, "error": "Internal server error"}

    def _find_org_admin_fallback(self, user_id: int, org_id: Optional[int]) -> Optional[tuple]:
        """
        SLA-007: Fallback when manager_id is NULL.

        Finds an admin or manager in the same organization to receive escalation.
        Returns (email, full_name) tuple or None.
        """
        if not org_id:
            return None

        logger.warning(f"No manager_id for user {user_id}, using org admin fallback")

        fallback = self.db.execute(text("""
            SELECT email, full_name
            FROM users
            WHERE organization_id = :org_id
            AND role IN ('admin', 'manager')
            AND email IS NOT NULL
            AND id != :uid
            ORDER BY
                CASE role WHEN 'admin' THEN 1 WHEN 'manager' THEN 2 ELSE 3 END,
                created_at ASC
            LIMIT 1
        """), {"org_id": org_id, "uid": user_id}).fetchone()

        return fallback

    def _send_escalation_notification(
        self,
        task_id: int,
        task_name: str,
        target_level: int,
        chain_config: Dict,
        user_id: int,
        org_id: Optional[int] = None,
        hours_overdue: float = 0,
    ):
        """Send escalation notification to the appropriate target."""
        try:
            target = chain_config["target"]

            # Determine recipient based on escalation target
            if target == "assignee":
                recipient = self.db.execute(text("""
                    SELECT email, full_name FROM users WHERE id = :uid
                """), {"uid": user_id}).fetchone()
            elif target == "manager":
                recipient = self.db.execute(text("""
                    SELECT m.email, m.full_name
                    FROM users u
                    LEFT JOIN users m ON m.id = u.manager_id
                    WHERE u.id = :uid AND m.email IS NOT NULL
                """), {"uid": user_id}).fetchone()
                # SLA-007: Fallback if manager_id is NULL
                if not recipient or not recipient[0]:
                    recipient = self._find_org_admin_fallback(user_id, org_id)
            elif target == "branch_manager":
                recipient = self.db.execute(text("""
                    SELECT m.email, m.full_name
                    FROM users u
                    LEFT JOIN users mgr ON mgr.id = u.manager_id
                    LEFT JOIN users m ON m.id = mgr.manager_id
                    WHERE u.id = :uid AND m.email IS NOT NULL
                """), {"uid": user_id}).fetchone()
                # SLA-007: Fallback if branch manager chain is NULL
                if not recipient or not recipient[0]:
                    recipient = self._find_org_admin_fallback(user_id, org_id)
            else:
                recipient = None

            if recipient and recipient[0]:
                from services.notification_service import NotificationService
                notifier = NotificationService()
                level_label = {1: "Reminder", 2: "Manager Escalation", 3: "Critical Escalation"}.get(target_level, "Alert")
                notifier.send_email(
                    to_email=recipient[0],
                    subject=f"[{level_label}] Overdue Task - {task_name}",
                    html_content=f"""
                    <h3>Task Escalation Alert (Level {target_level})</h3>
                    <p>A workflow task requires attention:</p>
                    <ul>
                        <li><strong>Task:</strong> {task_name}</li>
                        <li><strong>Overdue by:</strong> {hours_overdue:.0f} business hours</li>
                        <li><strong>Escalation Level:</strong> {target_level}/3</li>
                        <li><strong>Action Required:</strong> {chain_config['action'].replace('_', ' ').title()}</li>
                    </ul>
                    <p>Please review and take action immediately.</p>
                    """
                )
            else:
                logger.warning(
                    f"No recipient found for escalation of task {task_id} "
                    f"(target={target}, user_id={user_id}, org_id={org_id})"
                )
        except Exception as e:
            logger.warning(f"Could not send escalation notification for task {task_id}: {e}")

    # =========================================================================
    # DEAD LETTER: RETRY FAILED TASKS
    # =========================================================================

    # Maximum retries before a task is moved to dead letter.
    # Must stay in sync with WorkflowAIExecutor.MAX_TASK_RETRIES.
    MAX_TASK_RETRIES = 5

    def process_failed_tasks(self) -> Dict[str, Any]:
        """
        Retry workflow tasks that are in 'failed' status.

        Failed tasks with retry_count < MAX_TASK_RETRIES are reset to 'pending'
        so the AI executor picks them up on the next cycle.

        Tasks that have already exhausted retries (should already be 'dead_letter')
        are skipped. This method acts as a safety net in case _mark_task_failed
        did not promote a task to dead_letter correctly.

        Dead-letter tasks are never retried; they require manual intervention.
        """
        try:
            # Find failed tasks that are eligible for retry
            failed_tasks = self.db.execute(text("""
                SELECT
                    wti.id,
                    wti.task_name,
                    COALESCE(wti.retry_count, 0) as retry_count,
                    wti.error_message
                FROM workflow_task_instances wti
                JOIN workflow_instances wi ON wi.id = wti.workflow_instance_id
                WHERE wti.status = 'failed'
                AND wi.status = 'active'
                AND COALESCE(wti.retry_count, 0) < :max_retries
                LIMIT 50
            """), {"max_retries": self.MAX_TASK_RETRIES}).fetchall()

            retried = 0
            dead_lettered = 0

            for task in failed_tasks:
                task_id = task[0]
                task_name = task[1]
                retry_count = task[2]
                last_error = task[3]

                if retry_count >= self.MAX_TASK_RETRIES:
                    # Safety net: promote to dead_letter if somehow missed
                    self.db.execute(text("""
                        UPDATE workflow_task_instances
                        SET status = 'dead_letter',
                            health_status = 'broken',
                            error_message = :error,
                            updated_at = NOW()
                        WHERE id = :id AND status = 'failed'
                    """), {
                        "id": task_id,
                        "error": f"Dead letter (safety net): {(last_error or '')[:400]}",
                    })
                    dead_lettered += 1
                    logger.error(
                        f"Task {task_id} ({task_name}) moved to dead letter "
                        f"(safety net, retry_count={retry_count})"
                    )
                else:
                    # Reset to pending for retry
                    self.db.execute(text("""
                        UPDATE workflow_task_instances
                        SET status = 'pending',
                            health_status = 'healthy',
                            updated_at = NOW()
                        WHERE id = :id AND status = 'failed'
                    """), {"id": task_id})
                    retried += 1
                    logger.info(
                        f"Task {task_id} ({task_name}) reset to pending for retry "
                        f"(attempt {retry_count + 1}/{self.MAX_TASK_RETRIES})"
                    )

            if retried or dead_lettered:
                self.db.commit()

            logger.info(
                f"Failed task processing: {retried} retried, "
                f"{dead_lettered} moved to dead letter"
            )

            return {
                "success": True,
                "retried_count": retried,
                "dead_lettered_count": dead_lettered,
            }

        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"Failed task processing error: {e}")
            return {"success": False, "error": "Internal server error"}

    # =========================================================================
    # WORKFLOW COMPLETION CHECKS
    # =========================================================================

    def check_workflow_completions(self) -> Dict[str, Any]:
        """
        Check for workflows that should be marked as completed.

        Workflows are completed when:
        - All tasks are completed/skipped/cancelled
        - The entity has moved to a terminal status (funded, closed, etc.)
        """
        try:
            completed = 0

            # Check for workflows where all tasks are done
            ready_to_complete = self.db.execute(text("""
                SELECT wi.id
                FROM workflow_instances wi
                WHERE wi.status = 'active'
                AND NOT EXISTS (
                    SELECT 1 FROM workflow_task_instances wti
                    WHERE wti.workflow_instance_id = wi.id
                    AND wti.status IN ('scheduled', 'pending', 'in_progress', 'failed')
                )
                AND EXISTS (
                    SELECT 1 FROM workflow_task_instances wti2
                    WHERE wti2.workflow_instance_id = wi.id
                )
            """)).fetchall()

            workflow_service = self._get_workflow_service()

            for (instance_id,) in ready_to_complete:
                result = workflow_service.complete_workflow(instance_id)
                if result.get("success"):
                    completed += 1

            # Check for leads/loans that have moved to terminal status
            # This auto-cancels their workflows
            # Use actual LeadStage enum values
            terminal_leads = self.db.execute(text("""
                SELECT wi.id
                FROM workflow_instances wi
                JOIN leads l ON l.id = wi.lead_id
                WHERE wi.status = 'active'
                AND l.stage::text IN ('Closed', 'Withdrawn', 'Disclosed')
            """)).fetchall()

            for (instance_id,) in terminal_leads:
                workflow_service.cancel_workflow(
                    instance_id=instance_id,
                    reason="Lead reached terminal status",
                    user_id=1  # System user
                )
                completed += 1

            terminal_loans = self.db.execute(text("""
                SELECT wi.id
                FROM workflow_instances wi
                JOIN loans l ON l.id = wi.loan_id
                WHERE wi.status = 'active'
                AND l.stage::text = 'Funded'
            """)).fetchall()

            for (instance_id,) in terminal_loans:
                workflow_service.cancel_workflow(
                    instance_id=instance_id,
                    reason="Loan reached terminal status",
                    user_id=1  # System user
                )
                completed += 1

            logger.info(f"Completed/cancelled {completed} workflows")

            return {
                "success": True,
                "workflows_completed": completed
            }

        except Exception as e:
            self.db.rollback()
            logger.error(f"Workflow completion check failed: {e}")
            return {"success": False, "error": "Internal server error"}

    # =========================================================================
    # SCHEDULED RUN
    # =========================================================================

    def run_all_scheduled_tasks(self) -> Dict[str, Any]:
        """
        Run all scheduled workflow tasks.

        This is the main entry point for scheduled/cron execution.
        """
        start_time = datetime.now(timezone.utc)
        results = {
            "success": True,
            "started_at": start_time.isoformat(),
            "operations": {}
        }

        try:
            # 1. Process status changes for auto-enrollment
            status_result = self.process_status_changes()
            results["operations"]["status_changes"] = status_result

            # 2. Generate due tasks
            task_result = self.generate_due_tasks()
            results["operations"]["task_generation"] = task_result

            # 3. Retry failed tasks (dead letter mechanism)
            failed_result = self.process_failed_tasks()
            results["operations"]["failed_task_retries"] = failed_result

            # 4. Escalate overdue tasks
            escalation_result = self.escalate_overdue_tasks()
            results["operations"]["escalation"] = escalation_result

            # 5. Check workflow completions
            completion_result = self.check_workflow_completions()
            results["operations"]["completions"] = completion_result

            end_time = datetime.now(timezone.utc)
            results["completed_at"] = end_time.isoformat()
            results["duration_seconds"] = (end_time - start_time).total_seconds()

            logger.info(f"Scheduled workflow run completed in {results['duration_seconds']:.2f}s")

            return results

        except Exception as e:
            results["success"] = False
            results["error"] = str(e)
            logger.error(f"Scheduled workflow run failed: {e}")
            return results

    # =========================================================================
    # ASYNC BACKGROUND RUNNER
    # =========================================================================

    async def start_background_loop(self):
        """
        Start the background scheduler loop.

        Runs continuously, processing workflows at configured intervals.
        """
        self._running = True
        logger.info("Workflow scheduler background loop started")

        while self._running:
            try:
                # Run scheduled tasks
                self.run_all_scheduled_tasks()

                # Wait for next interval
                await asyncio.sleep(self.TASK_GENERATION_INTERVAL)

            except Exception as e:
                logger.error(f"Background loop error: {e}")
                await asyncio.sleep(60)  # Wait a bit before retrying

        logger.info("Workflow scheduler background loop stopped")

    def stop_background_loop(self):
        """Stop the background scheduler loop."""
        self._running = False


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def get_workflow_scheduler(db: Session) -> WorkflowScheduler:
    """Factory function to get a WorkflowScheduler instance."""
    return WorkflowScheduler(db)


def run_scheduled_workflow_tasks(db: Session) -> Dict[str, Any]:
    """
    Convenience function to run all scheduled workflow tasks.

    Can be called from a cron job or API endpoint.
    """
    scheduler = WorkflowScheduler(db)
    return scheduler.run_all_scheduled_tasks()


# =============================================================================
# EVENT-DRIVEN WORKFLOW TRIGGERS
# =============================================================================
# These functions provide immediate workflow enrollment after stage changes,
# eliminating the up-to-60-second delay from the scheduler polling loop.
# The scheduler still runs as a fallback; WorkflowSLAService.enroll_lead/loan
# deduplicates by checking for existing active workflows before creating new ones.
# =============================================================================

# Duplicated from WorkflowScheduler to avoid instantiating the full scheduler
# for a single-entity evaluation. Keep in sync with the maps above.
_LEAD_STATUS_WORKFLOW_MAP = {
    'New': 'prospect',
    'Attempted Contact': 'prospect',
    'Prospect': 'prospect',
    'Application': 'prequal',
    'Pre-Qualified': 'prequal',
    'Pre-Approved': 'pre_approved',
    'Does Not Qualify': 'credit_repair',
    'Credit Repair': 'credit_repair',
    'Long-Term Nurture': 'nurture',
    'Document Fulfillment': 'prequal',
}

_LEAD_SKIP_STAGES = {
    'Under Contract', 'Closed', 'Disclosed', 'Funded',
    'AMR', 'Referral Source', 'Do Not Call',
}

_LOAN_STAGE_WORKFLOW_MAP = {
    'DISCLOSED': 'under_contract',
    'PROCESSING': 'under_contract',
    'SUBMITTED': 'under_contract',
    'UW_RECEIVED': 'under_contract',
    'UNDERWRITING': 'under_contract',
    'CONDITIONAL_APPROVAL': 'under_contract',
    'APPROVED': 'under_contract',
    'CTC': 'last_mile',
    'CLEAR_TO_CLOSE': 'last_mile',
    'CLOSING': 'last_mile',
    'DOCS': 'last_mile',
    'DOCS_OUT': 'last_mile',
    'FUNDED': 'post_close',
}

_LOAN_SKIP_STAGES = {
    'SUSPENDED', 'CANCELLED', 'DENIED', 'DEAD',
    'WITHDRAWN', 'DOES_NOT_QUALIFY', 'NURTURE',
}


def trigger_workflow_evaluation_for_lead(
    db: Session,
    lead_id: int,
    new_stage: str,
    lead_source: Optional[str] = None,
    user_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Immediately evaluate workflow enrollment for a lead after a stage change.

    Called by lead update endpoints to avoid waiting for the scheduler poll.
    Best-effort: logs errors but never raises. The scheduler polling loop
    remains as a fallback, and WorkflowSLAService deduplicates enrollment.

    Args:
        db: Active database session (already committed with the stage change).
        lead_id: ID of the lead whose stage changed.
        new_stage: The new stage value (string).
        lead_source: Lead source string (for purchased lead detection).
        user_id: User who triggered the change (optional).

    Returns:
        Dict with result info (enrolled, skipped, or error).
    """
    try:
        if not new_stage:
            return {"status": "skipped", "reason": "no_stage"}

        # Normalize stage string
        stage = new_stage.strip()

        if stage in _LEAD_SKIP_STAGES:
            return {"status": "skipped", "reason": "skip_stage", "stage": stage}

        workflow_key = _LEAD_STATUS_WORKFLOW_MAP.get(stage)

        # Special case: purchased leads use lead_purchase workflow
        if lead_source and 'purchased' in lead_source.lower() and stage in ('New', 'Attempted Contact', 'Prospect'):
            workflow_key = 'lead_purchase'

        if not workflow_key:
            return {"status": "skipped", "reason": "unmapped_stage", "stage": stage}

        from services.workflow_sla_service import WorkflowSLAService
        workflow_service = WorkflowSLAService(db)
        result = workflow_service.enroll_lead(
            lead_id=lead_id,
            workflow_key=workflow_key,
            trigger_status=stage,
            user_id=user_id,
        )

        if result.get("success"):
            logger.info(
                f"Event-driven workflow enrollment: lead {lead_id} -> "
                f"workflow '{workflow_key}' (stage={stage})"
            )
            return {"status": "enrolled", "workflow_key": workflow_key, "result": result}
        else:
            error = result.get("error", "")
            if "already enrolled" in error.lower():
                return {"status": "skipped", "reason": "already_enrolled"}
            logger.warning(f"Workflow enrollment failed for lead {lead_id}: {error}")
            return {"status": "failed", "error": error}

    except Exception as e:
        logger.warning(f"Event-driven workflow trigger failed for lead {lead_id}: {e}")
        return {"status": "error", "error": str(e)}


def trigger_workflow_evaluation_for_loan(
    db: Session,
    loan_id: int,
    new_stage: str,
    user_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Immediately evaluate workflow enrollment for a loan after a stage change.

    Called by loan update endpoints to avoid waiting for the scheduler poll.
    Best-effort: logs errors but never raises. The scheduler polling loop
    remains as a fallback, and WorkflowSLAService deduplicates enrollment.

    Args:
        db: Active database session (already committed with the stage change).
        loan_id: ID of the loan whose stage changed.
        new_stage: The new stage value (string, UPPERCASE expected).
        user_id: User who triggered the change (optional).

    Returns:
        Dict with result info (enrolled, skipped, or error).
    """
    try:
        if not new_stage:
            return {"status": "skipped", "reason": "no_stage"}

        stage = new_stage.strip()

        if stage in _LOAN_SKIP_STAGES:
            return {"status": "skipped", "reason": "skip_stage", "stage": stage}

        workflow_key = _LOAN_STAGE_WORKFLOW_MAP.get(stage)
        if not workflow_key:
            return {"status": "skipped", "reason": "unmapped_stage", "stage": stage}

        from services.workflow_sla_service import WorkflowSLAService
        workflow_service = WorkflowSLAService(db)
        result = workflow_service.enroll_loan(
            loan_id=loan_id,
            workflow_key=workflow_key,
            trigger_status=stage,
            user_id=user_id,
        )

        if result.get("success"):
            logger.info(
                f"Event-driven workflow enrollment: loan {loan_id} -> "
                f"workflow '{workflow_key}' (stage={stage})"
            )
            return {"status": "enrolled", "workflow_key": workflow_key, "result": result}
        else:
            error = result.get("error", "")
            if "already enrolled" in error.lower():
                return {"status": "skipped", "reason": "already_enrolled"}
            logger.warning(f"Workflow enrollment failed for loan {loan_id}: {error}")
            return {"status": "failed", "error": error}

    except Exception as e:
        logger.warning(f"Event-driven workflow trigger failed for loan {loan_id}: {e}")
        return {"status": "error", "error": str(e)}
