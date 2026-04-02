"""
Workflow AI Confidence Evaluator

Evaluates workflow tasks for AI autonomous execution.
Calculates confidence scores based on multiple factors and determines
whether tasks should be auto-executed, queued for review, or escalated.

Key responsibilities:
- Calculate confidence scores for task execution
- Determine execution decision (auto, review, escalate)
- Track AI evaluation history
- Execute approved tasks via AI orchestrator
"""

import logging
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy import text
from sqlalchemy.orm import Session
import json
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


class WorkflowAIEvaluator:
    """
    Evaluates workflow tasks for AI autonomous execution.

    Uses multiple factors to calculate a confidence score:
    - Contact history and engagement quality
    - Template availability and match quality
    - Time since last contact
    - Lead/loan data completeness
    - Historical success rates for similar tasks
    """

    # Confidence thresholds
    AUTO_EXECUTE_THRESHOLD = Decimal("0.950")
    REVIEW_THRESHOLD = Decimal("0.700")
    ESCALATE_THRESHOLD = Decimal("0.400")

    # Factor weights (must sum to 1.0)
    FACTOR_WEIGHTS = {
        "contact_data_quality": Decimal("0.20"),
        "engagement_history": Decimal("0.15"),
        "template_match": Decimal("0.25"),
        "time_appropriateness": Decimal("0.15"),
        "historical_success": Decimal("0.15"),
        "data_completeness": Decimal("0.10"),
    }

    # Current model version for tracking
    MODEL_VERSION = "1.0.0"

    def __init__(self, db: Session):
        self.db = db

    def evaluate_task(
        self,
        task_instance_id: int,
        auto_execute: bool = False
    ) -> Dict[str, Any]:
        """
        Evaluate a workflow task for AI execution.

        Args:
            task_instance_id: Workflow task instance ID
            auto_execute: If True, execute if confidence meets threshold

        Returns:
            Dict with evaluation results and decision
        """
        try:
            # Get task instance details
            task = self._get_task_instance(task_instance_id)
            if not task:
                return {"success": False, "error": "Task instance not found"}

            # Check if task is eligible for AI
            if not task.get("ai_eligible"):
                return {
                    "success": False,
                    "error": "Task not eligible for AI execution",
                    "ai_eligible": False
                }

            # Get entity data
            entity_data = self._get_entity_data(task["lead_id"], task["loan_id"])

            # Calculate confidence factors
            factors = self._calculate_factors(task, entity_data)

            # Calculate overall confidence score
            confidence_score = self._calculate_confidence(factors)

            # Determine decision
            decision = self._determine_decision(confidence_score)

            # Record evaluation
            evaluation_id = self._record_evaluation(
                task_instance_id=task_instance_id,
                confidence_score=confidence_score,
                factors=factors,
                decision=decision
            )

            # Update task with confidence score
            self._update_task_confidence(task_instance_id, confidence_score)

            result = {
                "success": True,
                "task_instance_id": task_instance_id,
                "confidence_score": float(confidence_score),
                "factors": {k: float(v) for k, v in factors.items()},
                "decision": decision,
                "threshold_used": float(self.AUTO_EXECUTE_THRESHOLD),
                "evaluation_id": evaluation_id
            }

            # Auto-execute if requested and confidence is high enough
            if auto_execute and decision == "auto_execute":
                execution_result = self._execute_task(task)
                result["executed"] = execution_result.get("success", False)
                result["execution_result"] = execution_result

                # Update evaluation with execution result
                self._update_evaluation_execution(evaluation_id, execution_result)

            return result

        except Exception as e:
            logger.error(f"Task evaluation failed: {e}")
            return {"success": False, "error": "Internal server error"}

    def evaluate_batch(
        self,
        task_instance_ids: List[int],
        auto_execute: bool = False
    ) -> Dict[str, Any]:
        """
        Evaluate multiple tasks in batch.

        Args:
            task_instance_ids: List of task instance IDs
            auto_execute: If True, execute tasks that meet threshold

        Returns:
            Dict with batch evaluation results
        """
        results = {
            "success": True,
            "total": len(task_instance_ids),
            "evaluated": 0,
            "auto_execute": 0,
            "review": 0,
            "escalate": 0,
            "executed": 0,
            "errors": []
        }

        for task_id in task_instance_ids:
            try:
                result = self.evaluate_task(task_id, auto_execute=auto_execute)

                if result.get("success"):
                    results["evaluated"] += 1
                    decision = result.get("decision")

                    if decision == "auto_execute":
                        results["auto_execute"] += 1
                    elif decision == "queue_for_review":
                        results["review"] += 1
                    else:
                        results["escalate"] += 1

                    if result.get("executed"):
                        results["executed"] += 1
                else:
                    results["errors"].append({
                        "task_id": task_id,
                        "error": result.get("error")
                    })

            except Exception as e:
                results["errors"].append({
                    "task_id": task_id,
                    "error": "Internal server error"
                })

        return results

    def get_pending_ai_tasks(
        self,
        limit: int = 100,
        task_types: List[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get pending AI-eligible tasks that haven't been evaluated.

        Args:
            limit: Maximum tasks to return
            task_types: Filter by task types (email, text, etc.)

        Returns:
            List of task details
        """
        type_filter = ""
        params = {"limit": limit}

        if task_types:
            type_filter = "AND wti.task_type = ANY(:types)"
            params["types"] = task_types

        eval_query = (
            "SELECT"
            " wti.id, wti.task_name, wti.task_type,"
            " wti.lead_id, wti.loan_id,"
            " wti.scheduled_date, wti.ai_confidence"
            " FROM workflow_task_instances wti"
            " WHERE wti.ai_eligible = true"
            " AND wti.status IN ('scheduled', 'pending')"
            " AND wti.ai_confidence IS NULL"
            " " + type_filter
            + " ORDER BY wti.scheduled_date ASC"
            " LIMIT :limit"
        )
        results = self.db.execute(text(eval_query), params).fetchall()

        return [
            {
                "id": row[0],
                "task_name": row[1],
                "task_type": row[2],
                "lead_id": row[3],
                "loan_id": row[4],
                "scheduled_date": row[5].isoformat() if row[5] else None,
                "ai_confidence": float(row[6]) if row[6] else None
            }
            for row in results
        ]

    def _calculate_factors(
        self,
        task: Dict,
        entity_data: Dict
    ) -> Dict[str, Decimal]:
        """Calculate individual confidence factors."""
        factors = {}

        # 1. Contact data quality (email, phone availability and validity)
        factors["contact_data_quality"] = self._score_contact_quality(entity_data)

        # 2. Engagement history (past interactions, responses)
        factors["engagement_history"] = self._score_engagement_history(
            task["lead_id"], task["loan_id"]
        )

        # 3. Template match (availability of appropriate template)
        factors["template_match"] = self._score_template_match(
            task["task_type"],
            entity_data
        )

        # 4. Time appropriateness (business hours, last contact timing)
        factors["time_appropriateness"] = self._score_time_appropriateness(
            task, entity_data
        )

        # 5. Historical success rate for similar tasks
        factors["historical_success"] = self._score_historical_success(
            task["task_type"],
            task.get("workflow_id")
        )

        # 6. Data completeness (required fields for personalization)
        factors["data_completeness"] = self._score_data_completeness(entity_data)

        return factors

    def _calculate_confidence(self, factors: Dict[str, Decimal]) -> Decimal:
        """Calculate weighted confidence score."""
        total = Decimal("0")

        for factor_name, score in factors.items():
            weight = self.FACTOR_WEIGHTS.get(factor_name, Decimal("0"))
            total += score * weight

        # Ensure score is between 0 and 1
        return max(Decimal("0"), min(Decimal("1"), total))

    def _determine_decision(self, confidence: Decimal) -> str:
        """Determine execution decision based on confidence."""
        if confidence >= self.AUTO_EXECUTE_THRESHOLD:
            return "auto_execute"
        elif confidence >= self.REVIEW_THRESHOLD:
            return "queue_for_review"
        else:
            return "escalate"

    def _score_contact_quality(self, entity_data: Dict) -> Decimal:
        """Score contact data quality."""
        score = Decimal("0")

        # Email quality
        email = entity_data.get("email")
        if email:
            score += Decimal("0.4")
            # Bonus for non-generic email
            if not any(x in email.lower() for x in ["noreply", "donotreply", "test"]):
                score += Decimal("0.1")

        # Phone quality
        phone = entity_data.get("phone")
        if phone:
            score += Decimal("0.4")
            # Basic validation - has enough digits
            digits = "".join(c for c in phone if c.isdigit())
            if len(digits) >= 10:
                score += Decimal("0.1")

        return min(Decimal("1"), score)

    def _score_engagement_history(
        self,
        lead_id: int = None,
        loan_id: int = None
    ) -> Decimal:
        """Score based on past engagement."""
        # Check for recent positive interactions
        if lead_id:
            result = self.db.execute(text("""
                SELECT
                    COUNT(*) as total,
                    COUNT(CASE WHEN outcome = 'positive' THEN 1 END) as positive,
                    COUNT(CASE WHEN outcome = 'negative' THEN 1 END) as negative
                FROM lead_activities
                WHERE lead_id = :lead_id
                AND created_at >= NOW() - INTERVAL '30 days'
            """), {"lead_id": lead_id}).fetchone()

            if result and result[0] > 0:
                total, positive, negative = result
                if negative > positive:
                    return Decimal("0.3")  # Low score if mostly negative
                elif positive > 0:
                    return Decimal("0.8") + (Decimal(str(positive)) / Decimal("10"))
                else:
                    return Decimal("0.6")  # Neutral

        # Default moderate score
        return Decimal("0.5")

    def _score_template_match(
        self,
        task_type: str,
        entity_data: Dict
    ) -> Decimal:
        """Score template availability and match quality."""
        # Check for personalization data
        has_name = bool(entity_data.get("name"))
        has_email = bool(entity_data.get("email"))
        has_phone = bool(entity_data.get("phone"))

        if task_type in ["email", "text", "text_am", "text_pm"]:
            # These need good personalization data
            if has_name and (has_email if "email" in task_type else has_phone):
                return Decimal("0.9")
            elif has_name:
                return Decimal("0.7")
            else:
                return Decimal("0.4")

        # Phone tasks don't need templates
        return Decimal("0.8")

    def _score_time_appropriateness(
        self,
        task: Dict,
        entity_data: Dict
    ) -> Decimal:
        """Score based on timing factors."""
        now = datetime.now(timezone.utc)

        # Check business hours (9 AM - 6 PM local time assumed)
        hour = now.hour
        if 9 <= hour <= 18:
            time_score = Decimal("0.9")
        elif 7 <= hour <= 21:
            time_score = Decimal("0.6")
        else:
            time_score = Decimal("0.3")

        # Check if scheduled date has passed (task is due)
        scheduled = task.get("scheduled_date")
        if scheduled and scheduled <= now:
            time_score += Decimal("0.1")

        return min(Decimal("1"), time_score)

    def _score_historical_success(
        self,
        task_type: str,
        workflow_id: int = None
    ) -> Decimal:
        """Score based on historical success rate for similar tasks."""
        result = self.db.execute(text("""
            SELECT
                COUNT(*) as total,
                COUNT(CASE WHEN wac.executed AND wac.execution_result->>'success' = 'true' THEN 1 END) as success
            FROM workflow_ai_confidence wac
            JOIN workflow_task_instances wti ON wti.id = wac.workflow_task_instance_id
            WHERE wti.task_type = :task_type
            AND wac.created_at >= NOW() - INTERVAL '30 days'
        """), {"task_type": task_type}).fetchone()

        if result and result[0] > 10:  # Need enough data
            total, success = result
            success_rate = Decimal(str(success)) / Decimal(str(total))
            return max(Decimal("0.3"), success_rate)

        # Default to moderate confidence if not enough data
        return Decimal("0.6")

    def _score_data_completeness(self, entity_data: Dict) -> Decimal:
        """Score based on data completeness."""
        required_fields = ["name", "email", "phone"]
        optional_fields = ["property_type", "loan_purpose", "estimated_amount"]

        present_required = sum(1 for f in required_fields if entity_data.get(f))
        present_optional = sum(1 for f in optional_fields if entity_data.get(f))

        required_score = Decimal(str(present_required)) / Decimal(str(len(required_fields)))
        optional_score = Decimal(str(present_optional)) / Decimal(str(len(optional_fields))) * Decimal("0.3")

        return min(Decimal("1"), required_score * Decimal("0.7") + optional_score)

    def _get_task_instance(self, task_instance_id: int) -> Optional[Dict]:
        """Get task instance details."""
        result = self.db.execute(text("""
            SELECT
                wti.id, wti.workflow_instance_id, wti.workflow_id,
                wti.lead_id, wti.loan_id, wti.task_name, wti.task_type,
                wti.ai_eligible, wti.scheduled_date, wti.status
            FROM workflow_task_instances wti
            WHERE wti.id = :id
        """), {"id": task_instance_id}).fetchone()

        if not result:
            return None

        return {
            "id": result[0],
            "workflow_instance_id": result[1],
            "workflow_id": result[2],
            "lead_id": result[3],
            "loan_id": result[4],
            "task_name": result[5],
            "task_type": result[6],
            "ai_eligible": result[7],
            "scheduled_date": result[8],
            "status": result[9]
        }

    def _get_entity_data(
        self,
        lead_id: int = None,
        loan_id: int = None
    ) -> Dict[str, Any]:
        """Get entity data for evaluation."""
        data = {}

        if lead_id:
            result = self.db.execute(text("""
                SELECT first_name, last_name, email, phone,
                       property_type, loan_purpose, estimated_amount
                FROM leads WHERE id = :id
            """), {"id": lead_id}).fetchone()

            if result:
                data = {
                    "name": f"{result[0] or ''} {result[1] or ''}".strip(),
                    "email": result[2],
                    "phone": result[3],
                    "property_type": result[4],
                    "loan_purpose": result[5],
                    "estimated_amount": float(result[6]) if result[6] else None
                }

        elif loan_id:
            result = self.db.execute(text("""
                SELECT borrower_first_name, borrower_last_name,
                       borrower_email, borrower_phone,
                       property_type, loan_purpose, loan_amount
                FROM loans WHERE id = :id
            """), {"id": loan_id}).fetchone()

            if result:
                data = {
                    "name": f"{result[0] or ''} {result[1] or ''}".strip(),
                    "email": result[2],
                    "phone": result[3],
                    "property_type": result[4],
                    "loan_purpose": result[5],
                    "estimated_amount": float(result[6]) if result[6] else None
                }

        return data

    def _record_evaluation(
        self,
        task_instance_id: int,
        confidence_score: Decimal,
        factors: Dict[str, Decimal],
        decision: str
    ) -> int:
        """Record the AI evaluation."""
        self.db.execute(text("""
            INSERT INTO workflow_ai_confidence (
                workflow_task_instance_id,
                confidence_score,
                factors,
                decision,
                threshold_used,
                executed,
                model_version,
                created_at
            ) VALUES (
                :task_id, :score, :factors, :decision,
                :threshold, false, :model_version, NOW()
            )
        """), {
            "task_id": task_instance_id,
            "score": float(confidence_score),
            "factors": json.dumps({k: float(v) for k, v in factors.items()}),
            "decision": decision,
            "threshold": float(self.AUTO_EXECUTE_THRESHOLD),
            "model_version": self.MODEL_VERSION
        })
        self.db.flush()

        # Get the ID
        result = self.db.execute(text("""
            SELECT id FROM workflow_ai_confidence
            WHERE workflow_task_instance_id = :task_id
            ORDER BY id DESC LIMIT 1
        """), {"task_id": task_instance_id}).fetchone()

        return result[0] if result else None

    def _update_task_confidence(
        self,
        task_instance_id: int,
        confidence_score: Decimal
    ):
        """Update task instance with confidence score."""
        self.db.execute(text("""
            UPDATE workflow_task_instances
            SET ai_confidence = :score, updated_at = NOW()
            WHERE id = :id
        """), {"id": task_instance_id, "score": float(confidence_score)})

    def _update_evaluation_execution(
        self,
        evaluation_id: int,
        execution_result: Dict
    ):
        """Update evaluation with execution result."""
        self.db.execute(text("""
            UPDATE workflow_ai_confidence
            SET executed = true,
                execution_result = :result
            WHERE id = :id
        """), {
            "id": evaluation_id,
            "result": json.dumps(execution_result)
        })
        self.db.flush()  # Let the caller (route handler) commit the transaction

    def _execute_task(self, task: Dict) -> Dict[str, Any]:
        """Execute a task via AI."""
        try:
            task_type = task.get("task_type")

            if task_type in ["email"]:
                return self._execute_email_task(task)
            elif task_type in ["text", "text_am", "text_pm"]:
                return self._execute_sms_task(task)
            else:
                return {"success": False, "error": f"Task type {task_type} not supported for AI execution"}

        except SQLAlchemyError as e:
            logger.error(f"AI task execution failed: {e}")
            return {"success": False, "error": "Internal server error"}

    def _execute_email_task(self, task: Dict) -> Dict[str, Any]:
        """Execute an email task via AI."""
        try:
            # Get entity data
            entity_data = self._get_entity_data(task["lead_id"], task["loan_id"])

            if not entity_data.get("email"):
                return {"success": False, "error": "No email address available"}

            # Use AI orchestrator to send email
            # This integrates with the existing AI agent system
            from agents.orchestrator import run_orchestrator

            prompt = f"""Send a workflow follow-up email to {entity_data['name']} at {entity_data['email']}.
Task: {task['task_name']}
Context: This is an automated workflow task for lead/loan follow-up."""

            result = run_orchestrator(
                user_message=prompt,
                user_id="system",
                lead_id=task.get("lead_id"),
                loan_id=task.get("loan_id"),
                task_source="workflow",
                workflow_task_instance_id=task["id"]
            )

            # Update task status
            self.db.execute(text("""
                UPDATE workflow_task_instances
                SET status = 'completed',
                    completion_source = 'ai',
                    ai_executed_at = NOW(),
                    completed_at = NOW(),
                    updated_at = NOW()
                WHERE id = :id
            """), {"id": task["id"]})
            self.db.flush()  # Let the caller (route handler) commit the transaction

            return {"success": True, "result": result}

        except SQLAlchemyError as e:
            logger.error(f"Email task execution failed: {e}")
            return {"success": False, "error": "Internal server error"}

    def _execute_sms_task(self, task: Dict) -> Dict[str, Any]:
        """Execute an SMS task via AI."""
        try:
            # Get entity data
            entity_data = self._get_entity_data(task["lead_id"], task["loan_id"])

            if not entity_data.get("phone"):
                return {"success": False, "error": "No phone number available"}

            # Use AI orchestrator to send SMS
            from agents.orchestrator import run_orchestrator

            prompt = f"""Send a workflow follow-up text message to {entity_data['name']} at {entity_data['phone']}.
Task: {task['task_name']}
Context: This is an automated workflow task. Keep the message brief and professional."""

            result = run_orchestrator(
                user_message=prompt,
                user_id="system",
                lead_id=task.get("lead_id"),
                loan_id=task.get("loan_id"),
                task_source="workflow",
                workflow_task_instance_id=task["id"]
            )

            # Update task status
            self.db.execute(text("""
                UPDATE workflow_task_instances
                SET status = 'completed',
                    completion_source = 'ai',
                    ai_executed_at = NOW(),
                    completed_at = NOW(),
                    updated_at = NOW()
                WHERE id = :id
            """), {"id": task["id"]})
            self.db.flush()  # Let the caller (route handler) commit the transaction

            return {"success": True, "result": result}

        except SQLAlchemyError as e:
            logger.error(f"SMS task execution failed: {e}")
            return {"success": False, "error": "Internal server error"}


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def get_ai_evaluator(db: Session) -> WorkflowAIEvaluator:
    """Factory function to get a WorkflowAIEvaluator instance."""
    return WorkflowAIEvaluator(db)


def evaluate_and_execute_tasks(db: Session, limit: int = 50) -> Dict[str, Any]:
    """
    Evaluate and auto-execute pending AI tasks.

    Convenience function for scheduled execution.
    """
    evaluator = WorkflowAIEvaluator(db)

    # Get pending AI tasks
    pending = evaluator.get_pending_ai_tasks(limit=limit)

    if not pending:
        return {"success": True, "message": "No pending AI tasks", "evaluated": 0}

    # Evaluate and execute
    task_ids = [t["id"] for t in pending]
    return evaluator.evaluate_batch(task_ids, auto_execute=True)
