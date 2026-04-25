"""
Workflow AI Task Executor

Executes workflow tasks autonomously using the AI Orchestrator.
Handles text, email, and other AI-routable task types.

Integrates with:
- WorkflowAIEvaluator for confidence scoring
- AI Orchestrator for task execution
- WebSocket notifier for real-time updates
"""

import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

# Circuit breaker: maximum number of tool calls per batch/autonomous execution cycle.
# Prevents runaway LLM tool-calling loops from consuming unbounded resources.
MAX_TOOL_CALLS = 10


class WorkflowAIExecutor:
    """
    Executes workflow tasks using AI automation.

    Supports autonomous execution of:
    - Text messages (SMS)
    - Email outreach
    - AI-generated content

    All executions go through confidence evaluation first.
    """

    # Task types that can be executed by AI
    AI_EXECUTABLE_TYPES = ['text', 'text_am', 'text_pm', 'email', 'ai_autonomous']

    # Minimum confidence for auto-execution
    AUTO_EXECUTE_THRESHOLD = 0.950

    def __init__(self, db: Session):
        self.db = db
        self._evaluator = None
        self._notifier = None

    def _get_evaluator(self):
        """Lazy load evaluator."""
        if self._evaluator is None:
            from services.workflow_ai_evaluator import WorkflowAIEvaluator
            self._evaluator = WorkflowAIEvaluator(self.db)
        return self._evaluator

    def _get_notifier(self):
        """Lazy load notifier."""
        if self._notifier is None:
            from services.workflow_websocket_events import get_workflow_notifier
            self._notifier = get_workflow_notifier()
        return self._notifier

    def execute_task(
        self,
        task_instance_id: int,
        force_execute: bool = False,
        user_override: bool = False,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Execute a single workflow task via AI.

        Args:
            task_instance_id: Workflow task instance ID
            force_execute: Skip confidence check and execute
            user_override: User approved execution despite low confidence
            context: Additional context for execution

        Returns:
            Dict with execution result
        """
        try:
            # Get task details
            task = self._get_task_details(task_instance_id)
            if not task:
                return {"success": False, "error": "Task not found"}

            # Verify task is eligible for AI execution
            if task["task_type"] not in self.AI_EXECUTABLE_TYPES:
                return {
                    "success": False,
                    "error": f"Task type '{task['task_type']}' is not AI-executable"
                }

            if task["status"] not in ['scheduled', 'pending']:
                return {
                    "success": False,
                    "error": f"Task status '{task['status']}' is not executable"
                }

            # Evaluate confidence if not forcing
            confidence_result = None
            if not force_execute:
                evaluator = self._get_evaluator()
                confidence_result = evaluator.evaluate_task(task_instance_id, auto_execute=False)

                if not confidence_result.get("success"):
                    return {"success": False, "error": "Confidence evaluation failed"}

                confidence = confidence_result["confidence_score"]

                # Check if we should auto-execute
                if not user_override and confidence < self.AUTO_EXECUTE_THRESHOLD:
                    return {
                        "success": False,
                        "error": "Confidence too low for auto-execution",
                        "confidence_score": confidence,
                        "recommendation": confidence_result.get("recommendation"),
                        "requires_approval": True
                    }

            # Execute based on task type
            if task["task_type"] in ['text', 'text_am', 'text_pm']:
                result = self._execute_text_task(task, context)
            elif task["task_type"] == 'email':
                result = self._execute_email_task(task, context)
            else:
                result = self._execute_generic_ai_task(task, context)

            # Update task status based on result
            if result.get("success"):
                self._mark_task_completed(task_instance_id, "ai", result)

                # Notify via WebSocket
                notifier = self._get_notifier()
                notifier.notify_user_sync(
                    task["assigned_user_id"],
                    {
                        "type": "ai_task_executed",
                        "task_instance_id": task_instance_id,
                        "task_name": task["task_name"],
                        "task_type": task["task_type"],
                        "success": True,
                        "result_summary": result.get("summary"),
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                )
            else:
                self._mark_task_failed(task_instance_id, result.get("error", "Execution failed"))

            result["task_instance_id"] = task_instance_id
            result["task_name"] = task["task_name"]
            if confidence_result:
                result["confidence_score"] = confidence_result.get("confidence_score")

            return result

        except Exception as e:
            logger.error(f"AI task execution failed: {e}")
            return {"success": False, "error": "Internal server error"}

    def execute_batch(
        self,
        task_instance_ids: List[int],
        auto_only: bool = True
    ) -> Dict[str, Any]:
        """
        Execute multiple tasks in batch.

        Args:
            task_instance_ids: List of task IDs to execute
            auto_only: Only execute tasks that pass confidence threshold

        Returns:
            Dict with batch results
        """
        results = {
            "success": True,
            "executed": [],
            "skipped": [],
            "failed": [],
            "total": len(task_instance_ids),
            "circuit_breaker_tripped": False
        }

        tool_call_count = 0
        for task_id in task_instance_ids:
            tool_call_count += 1
            if tool_call_count > MAX_TOOL_CALLS:
                logger.warning(
                    f"Circuit breaker: max tool calls ({MAX_TOOL_CALLS}) reached "
                    f"during batch execution. {len(task_instance_ids) - tool_call_count + 1} "
                    f"remaining tasks flagged for manual review."
                )
                results["circuit_breaker_tripped"] = True
                # Flag all remaining tasks for manual review instead of executing
                remaining_ids = task_instance_ids[tool_call_count - 1:]
                for remaining_id in remaining_ids:
                    self._mark_task_needs_review(
                        remaining_id,
                        f"Circuit breaker tripped: max tool calls ({MAX_TOOL_CALLS}) "
                        f"reached in batch execution"
                    )
                    results["skipped"].append({
                        "task_instance_id": remaining_id,
                        "reason": "Circuit breaker: max tool calls reached, flagged for manual review"
                    })
                break

            try:
                result = self.execute_task(
                    task_instance_id=task_id,
                    force_execute=not auto_only
                )

                if result.get("success"):
                    results["executed"].append({
                        "task_instance_id": task_id,
                        "task_name": result.get("task_name"),
                        "result": result.get("summary")
                    })
                elif result.get("requires_approval"):
                    results["skipped"].append({
                        "task_instance_id": task_id,
                        "task_name": result.get("task_name"),
                        "reason": "Requires approval",
                        "confidence": result.get("confidence_score")
                    })
                else:
                    results["failed"].append({
                        "task_instance_id": task_id,
                        "error": result.get("error")
                    })

            except Exception as e:
                results["failed"].append({
                    "task_instance_id": task_id,
                    "error": "Internal server error"
                })

        results["executed_count"] = len(results["executed"])
        results["skipped_count"] = len(results["skipped"])
        results["failed_count"] = len(results["failed"])

        if results["circuit_breaker_tripped"]:
            logger.warning(
                f"Batch execution (CIRCUIT BREAKER TRIPPED): {results['executed_count']} executed, "
                f"{results['skipped_count']} skipped/needs-review, {results['failed_count']} failed"
            )
        else:
            logger.info(
                f"Batch execution: {results['executed_count']} executed, "
                f"{results['skipped_count']} skipped, {results['failed_count']} failed"
            )

        return results

    def get_ready_for_execution(
        self,
        user_id: Optional[int] = None,
        task_types: Optional[List[str]] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get tasks ready for AI execution.

        Args:
            user_id: Filter by assigned user
            task_types: Filter by task types
            limit: Maximum results

        Returns:
            List of tasks with confidence pre-evaluated
        """
        if task_types is None:
            task_types = self.AI_EXECUTABLE_TYPES

        params = {"task_types": task_types, "limit": limit}
        filters = [
            "wti.task_type = ANY(:task_types)",
            "wti.status IN ('scheduled', 'pending')",
            "wti.route = 'ai_autonomous'",
            "wti.scheduled_date <= NOW()"
        ]

        if user_id:
            filters.append("wti.assigned_user_id = :user_id")
            params["user_id"] = user_id

        where_clause = " AND ".join(filters)

        exec_query = (
            "SELECT"
            " wti.id, wti.task_name, wti.task_type,"
            " wti.lead_id, wti.loan_id, wti.assigned_user_id,"
            " wti.scheduled_date,"
            " wac.confidence_score, wac.recommendation,"
            " COALESCE(l.first_name || ' ' || l.last_name, lo.borrower_name) as contact_name,"
            " COALESCE(l.phone, lo.borrower_phone) as contact_phone,"
            " COALESCE(l.email, lo.borrower_email) as contact_email"
            " FROM workflow_task_instances wti"
            " LEFT JOIN workflow_ai_confidence wac ON wac.task_instance_id = wti.id"
            " LEFT JOIN leads l ON l.id = wti.lead_id"
            " LEFT JOIN loans lo ON lo.id = wti.loan_id"
            " WHERE " + where_clause
            + " ORDER BY"
            " CASE WHEN wac.confidence_score >= 0.95 THEN 0 ELSE 1 END,"
            " wti.scheduled_date ASC"
            " LIMIT :limit"
        )
        results = self.db.execute(text(exec_query), params).fetchall()

        tasks = []
        for row in results:
            tasks.append({
                "task_instance_id": row[0],
                "task_name": row[1],
                "task_type": row[2],
                "lead_id": row[3],
                "loan_id": row[4],
                "assigned_user_id": row[5],
                "scheduled_date": row[6].isoformat() if row[6] else None,
                "confidence_score": float(row[7]) if row[7] else None,
                "recommendation": row[8],
                "contact_name": row[9],
                "contact_phone": row[10],
                "contact_email": row[11],
                "auto_executable": row[7] and float(row[7]) >= self.AUTO_EXECUTE_THRESHOLD
            })

        return tasks

    def run_autonomous_execution(
        self,
        user_id: Optional[int] = None,
        max_tasks: int = 20
    ) -> Dict[str, Any]:
        """
        Run autonomous execution cycle for high-confidence tasks.

        Called by scheduler to process AI-routable tasks that meet
        confidence threshold without human intervention.

        Args:
            user_id: Optionally filter by user
            max_tasks: Maximum tasks to process per cycle

        Returns:
            Dict with execution summary
        """
        try:
            # Get tasks ready for autonomous execution
            ready_tasks = self.get_ready_for_execution(
                user_id=user_id,
                limit=max_tasks
            )

            # Filter to only auto-executable
            auto_tasks = [t for t in ready_tasks if t.get("auto_executable")]

            if not auto_tasks:
                return {
                    "success": True,
                    "message": "No tasks ready for autonomous execution",
                    "tasks_checked": len(ready_tasks),
                    "tasks_executed": 0
                }

            # Execute batch
            task_ids = [t["task_instance_id"] for t in auto_tasks]
            result = self.execute_batch(task_ids, auto_only=True)

            result["tasks_checked"] = len(ready_tasks)
            result["message"] = f"Executed {result['executed_count']} tasks autonomously"

            return result

        except SQLAlchemyError as e:
            logger.error(f"Autonomous execution failed: {e}")
            return {"success": False, "error": "Internal server error"}

    def _get_task_details(self, task_instance_id: int) -> Optional[Dict[str, Any]]:
        """Get task details for execution."""
        result = self.db.execute(text("""
            SELECT
                wti.id,
                wti.task_name,
                wti.task_type,
                wti.status,
                wti.lead_id,
                wti.loan_id,
                wti.assigned_user_id,
                wti.workflow_instance_id,
                wti.task_group_key,
                wtc.task_key,
                wtc.metadata as task_config_metadata,
                COALESCE(l.first_name, lo.borrower_first_name) as first_name,
                COALESCE(l.last_name, lo.borrower_last_name) as last_name,
                COALESCE(l.phone, lo.borrower_phone) as phone,
                COALESCE(l.email, lo.borrower_email) as email
            FROM workflow_task_instances wti
            LEFT JOIN workflow_task_configs wtc ON wtc.id = wti.task_config_id
            LEFT JOIN leads l ON l.id = wti.lead_id
            LEFT JOIN loans lo ON lo.id = wti.loan_id
            WHERE wti.id = :task_id
        """), {"task_id": task_instance_id}).fetchone()

        if not result:
            return None

        return {
            "id": result[0],
            "task_name": result[1],
            "task_type": result[2],
            "status": result[3],
            "lead_id": result[4],
            "loan_id": result[5],
            "assigned_user_id": result[6],
            "workflow_instance_id": result[7],
            "task_group_key": result[8],
            "task_key": result[9],
            "config_metadata": result[10],
            "first_name": result[11],
            "last_name": result[12],
            "phone": result[13],
            "email": result[14],
            "contact_name": f"{result[11] or ''} {result[12] or ''}".strip() or "Contact"
        }

    def _execute_text_task(
        self,
        task: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Execute a text/SMS task."""
        try:
            if not task.get("phone"):
                return {"success": False, "error": "No phone number available"}

            # Generate message using AI
            message_content = self._generate_text_content(task, context)

            if not message_content:
                return {"success": False, "error": "Failed to generate message content"}

            # Send via SMS service
            from integrations.sms_service import get_sms_client
            from db import SessionLocal
            _sms_db = SessionLocal()
            try:
                sms_client = get_sms_client(db=_sms_db, user_id=task.get("assigned_user_id"))
                result = sms_client.send_sms(
                    to_phone=task["phone"],
                    message=message_content,
                    lead_id=task.get("lead_id"),
                    user_id=task.get("assigned_user_id")
                )
            finally:
                _sms_db.close()

            if result.get("success"):
                return {
                    "success": True,
                    "summary": f"Sent SMS to {task['contact_name']}",
                    "message_content": message_content,
                    "sms_id": result.get("message_id")
                }
            else:
                return {"success": False, "error": result.get("error", "SMS send failed")}

        except ImportError:
            logger.warning("SMS service not available, simulating send")
            return {
                "success": True,
                "summary": f"[SIMULATED] SMS to {task['contact_name']}",
                "simulated": True
            }
        except Exception as e:
            return {"success": False, "error": "Internal server error"}

    def _execute_email_task(
        self,
        task: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Execute an email task."""
        try:
            if not task.get("email"):
                return {"success": False, "error": "No email address available"}

            # Generate email content using AI
            email_content = self._generate_email_content(task, context)

            if not email_content:
                return {"success": False, "error": "Failed to generate email content"}

            # Send via email service
            from services.email_service import send_email

            result = send_email(
                to_email=task["email"],
                subject=email_content.get("subject", task["task_name"]),
                body=email_content.get("body", ""),
                lead_id=task.get("lead_id"),
                loan_id=task.get("loan_id"),
                user_id=task.get("assigned_user_id")
            )

            if result.get("success"):
                return {
                    "success": True,
                    "summary": f"Sent email to {task['contact_name']}",
                    "subject": email_content.get("subject"),
                    "email_id": result.get("email_id")
                }
            else:
                return {"success": False, "error": result.get("error", "Email send failed")}

        except ImportError:
            logger.warning("Email service not available, simulating send")
            return {
                "success": True,
                "summary": f"[SIMULATED] Email to {task['contact_name']}",
                "simulated": True
            }
        except Exception as e:
            return {"success": False, "error": "Internal server error"}

    def _execute_generic_ai_task(
        self,
        task: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Execute a generic AI task via orchestrator."""
        try:
            from agents.orchestrator import run_orchestrator

            # Build prompt for AI
            prompt = self._build_task_prompt(task, context)

            # Run through orchestrator — safely handle both sync and async contexts.
            # This method is sync but may be called from an async FastAPI handler,
            # so asyncio.run() would crash with "cannot be called from a running event loop".
            import asyncio
            import concurrent.futures

            coro = run_orchestrator(
                message=prompt,
                user_id=str(task.get("assigned_user_id", "system")),
                user_email="ai-executor@system.local",
                user_role="ai_agent",
                autonomous_mode=True
            )

            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                # Already inside an async event loop (e.g. FastAPI handler) —
                # run the coroutine in a separate thread with its own event loop.
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    result = pool.submit(asyncio.run, coro).result()
            else:
                # No running loop — safe to use asyncio.run() directly.
                result = asyncio.run(coro)

            return {
                "success": True,
                "summary": f"AI executed: {task['task_name']}",
                "response": result.get("response", "")[:500]
            }

        except Exception as e:
            logger.error(f"Generic AI task execution failed: {e}")
            return {"success": False, "error": "Internal server error"}

    def _generate_text_content(
        self,
        task: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """Generate SMS content for a task."""
        # Use template if available in config
        config_meta = task.get("config_metadata") or {}
        template = config_meta.get("sms_template")

        if template:
            # Simple template substitution
            return template.format(
                first_name=task.get("first_name", "there"),
                contact_name=task.get("contact_name", "there")
            )

        # Generate via AI if no template
        task_name = task.get("task_name", "follow-up")
        first_name = task.get("first_name", "there")

        # Default templates by task type
        templates = {
            "text": f"Hi {first_name}, just checking in. Let me know if you have any questions about your mortgage application!",
            "text_am": f"Good morning {first_name}! Hope you're having a great day. Any questions I can help with?",
            "text_pm": f"Hi {first_name}, following up on your loan application. Feel free to reach out if you need anything!",
        }

        return templates.get(task.get("task_type"), templates["text"])

    def _generate_email_content(
        self,
        task: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, str]]:
        """Generate email content for a task."""
        config_meta = task.get("config_metadata") or {}

        # Use template if available
        subject_template = config_meta.get("email_subject")
        body_template = config_meta.get("email_body")

        first_name = task.get("first_name", "there")
        task_name = task.get("task_name", "Follow-up")

        subject = subject_template or f"Following up - {task_name}"
        body = body_template or f"""Hi {first_name},

I wanted to follow up on your mortgage application and see if you have any questions.

Please don't hesitate to reach out if there's anything I can help with.

Best regards"""

        return {
            "subject": subject,
            "body": body
        }

    def _build_task_prompt(
        self,
        task: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """Build AI prompt for task execution."""
        return f"""Execute workflow task: {task['task_name']}

Task Type: {task['task_type']}
Contact: {task.get('contact_name', 'Unknown')}
Lead ID: {task.get('lead_id', 'N/A')}
Loan ID: {task.get('loan_id', 'N/A')}

Please complete this task appropriately."""

    def _mark_task_completed(
        self,
        task_instance_id: int,
        completion_source: str,
        result: Dict[str, Any]
    ):
        """Mark task as completed."""
        self.db.execute(text("""
            UPDATE workflow_task_instances
            SET status = 'completed',
                completion_source = :source,
                completed_at = NOW(),
                updated_at = NOW()
            WHERE id = :id
        """), {
            "id": task_instance_id,
            "source": completion_source
        })
        self.db.commit()

    # Maximum retries before a task is moved to dead letter
    MAX_TASK_RETRIES = 5

    def _mark_task_failed(self, task_instance_id: int, error: str):
        """
        Mark task as failed with retry tracking.

        Increments retry_count on each failure. When retry_count reaches
        MAX_TASK_RETRIES, the task is moved to 'dead_letter' status and
        will no longer be retried by the scheduler.
        """
        # Atomically increment retry_count and fetch the new value
        result = self.db.execute(text("""
            UPDATE workflow_task_instances
            SET retry_count = COALESCE(retry_count, 0) + 1,
                error_message = :error,
                last_failed_at = NOW(),
                updated_at = NOW()
            WHERE id = :id
            RETURNING retry_count
        """), {
            "id": task_instance_id,
            "error": error[:500],
        })
        row = result.fetchone()
        retry_count = row[0] if row else 1

        if retry_count >= self.MAX_TASK_RETRIES:
            # Move to dead letter -- permanently failed
            self.db.execute(text("""
                UPDATE workflow_task_instances
                SET status = 'dead_letter',
                    health_status = 'broken',
                    error_message = :error,
                    updated_at = NOW()
                WHERE id = :id
            """), {
                "id": task_instance_id,
                "error": f"Dead letter after {retry_count} retries. Last error: {error[:400]}",
            })
            logger.error(
                f"Task {task_instance_id} moved to dead letter after "
                f"{retry_count} retries. Last error: {error}"
            )

            # Create a broken task alert for admin visibility
            try:
                self.db.execute(text("""
                    INSERT INTO broken_task_alerts (
                        workflow_id, task_instance_id, alert_type,
                        alert_message, severity, created_at
                    )
                    SELECT
                        wti.workflow_id, wti.id, 'dead_letter',
                        :message, 'critical', NOW()
                    FROM workflow_task_instances wti
                    WHERE wti.id = :id
                """), {
                    "id": task_instance_id,
                    "message": (
                        f"Task permanently failed after {retry_count} retries. "
                        f"Last error: {error[:300]}"
                    ),
                })
            except Exception as alert_err:
                logger.warning(
                    f"Failed to create dead letter alert for task "
                    f"{task_instance_id}: {alert_err}"
                )
        else:
            # Keep as failed -- scheduler will retry on next cycle
            self.db.execute(text("""
                UPDATE workflow_task_instances
                SET status = 'failed',
                    health_status = 'broken',
                    updated_at = NOW()
                WHERE id = :id
            """), {
                "id": task_instance_id,
            })
            logger.warning(
                f"Task {task_instance_id} failed (attempt "
                f"{retry_count}/{self.MAX_TASK_RETRIES}): {error}"
            )

        self.db.commit()

    def _mark_task_needs_review(self, task_instance_id: int, reason: str):
        """Mark task as needing manual review (circuit breaker or other safety stop)."""
        try:
            self.db.execute(text("""
                UPDATE workflow_task_instances
                SET status = 'pending',
                    error_message = :reason,
                    health_status = 'needs_review',
                    route = 'manual',
                    updated_at = NOW()
                WHERE id = :id
            """), {
                "id": task_instance_id,
                "reason": reason[:500]
            })
            self.db.commit()
        except SQLAlchemyError as e:
            logger.error(f"Failed to mark task {task_instance_id} for review: {e}")
            self.db.rollback()


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def get_ai_executor(db: Session) -> WorkflowAIExecutor:
    """Factory function to get a WorkflowAIExecutor instance."""
    return WorkflowAIExecutor(db)


def run_autonomous_ai_tasks(db: Session, max_tasks: int = 20) -> Dict[str, Any]:
    """
    Convenience function to run autonomous AI task execution.

    Can be called from scheduler or API endpoint.
    """
    executor = WorkflowAIExecutor(db)
    return executor.run_autonomous_execution(max_tasks=max_tasks)
