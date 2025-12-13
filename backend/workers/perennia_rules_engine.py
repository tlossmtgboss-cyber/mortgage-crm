"""
Perennia Docs Rules Engine Worker

Executes automation rules based on document events.

Features:
- Event-driven rule execution
- Condition evaluation
- Action execution (auto-approve, notify, webhook)
- Rule priority ordering
"""

import os
import logging
import requests
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass
from enum import Enum

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class Operator(str, Enum):
    """Condition operators."""
    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    GREATER_THAN = "greater_than"
    LESS_THAN = "less_than"
    GREATER_EQUAL = "greater_equal"
    LESS_EQUAL = "less_equal"
    CONTAINS = "contains"
    NOT_CONTAINS = "not_contains"
    IN = "in"
    NOT_IN = "not_in"
    IS_NULL = "is_null"
    IS_NOT_NULL = "is_not_null"


class ActionType(str, Enum):
    """Action types that rules can execute."""
    AUTO_APPROVE = "auto_approve"
    REJECT = "reject"
    FLAG_FOR_REVIEW = "flag_for_review"
    CREATE_NOTIFICATION = "create_notification"
    SEND_WEBHOOK = "send_webhook"
    UPDATE_FIELD = "update_field"
    CREATE_TASK = "create_task"


@dataclass
class RuleResult:
    """Result of rule execution."""
    rule_id: int
    rule_name: str
    matched: bool
    actions_executed: List[str]
    error: Optional[str] = None


class ConditionEvaluator:
    """Evaluates rule conditions against document/event data."""

    def evaluate(
        self,
        conditions: List[Dict[str, Any]],
        context: Dict[str, Any]
    ) -> bool:
        """
        Evaluate all conditions (AND logic).

        Args:
            conditions: List of condition definitions
            context: Data to evaluate against

        Returns:
            True if all conditions match
        """
        for condition in conditions:
            if not self._evaluate_single(condition, context):
                return False
        return True

    def _evaluate_single(self, condition: Dict[str, Any], context: Dict[str, Any]) -> bool:
        """Evaluate a single condition."""
        field = condition.get("field")
        operator = condition.get("operator")
        value = condition.get("value")

        # Get field value from context
        field_value = self._get_field_value(field, context)

        try:
            if operator == Operator.EQUALS.value:
                return field_value == value
            elif operator == Operator.NOT_EQUALS.value:
                return field_value != value
            elif operator == Operator.GREATER_THAN.value:
                return float(field_value) > float(value)
            elif operator == Operator.LESS_THAN.value:
                return float(field_value) < float(value)
            elif operator == Operator.GREATER_EQUAL.value:
                return float(field_value) >= float(value)
            elif operator == Operator.LESS_EQUAL.value:
                return float(field_value) <= float(value)
            elif operator == Operator.CONTAINS.value:
                return value in str(field_value)
            elif operator == Operator.NOT_CONTAINS.value:
                return value not in str(field_value)
            elif operator == Operator.IN.value:
                return field_value in value
            elif operator == Operator.NOT_IN.value:
                return field_value not in value
            elif operator == Operator.IS_NULL.value:
                return field_value is None
            elif operator == Operator.IS_NOT_NULL.value:
                return field_value is not None
            else:
                logger.warning(f"Unknown operator: {operator}")
                return False
        except (ValueError, TypeError) as e:
            logger.warning(f"Condition evaluation error: {e}")
            return False

    def _get_field_value(self, field: str, context: Dict[str, Any]) -> Any:
        """Get nested field value from context."""
        parts = field.split(".")
        value = context

        for part in parts:
            if isinstance(value, dict):
                value = value.get(part)
            else:
                return None

        return value


class ActionExecutor:
    """Executes rule actions."""

    def __init__(self, db: Session):
        self.db = db

    def execute(
        self,
        action: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute an action.

        Args:
            action: Action definition
            context: Event/document context

        Returns:
            Dict with execution result
        """
        action_type = action.get("type")
        params = action.get("params", {})

        try:
            if action_type == ActionType.AUTO_APPROVE.value:
                return self._auto_approve(context, params)
            elif action_type == ActionType.REJECT.value:
                return self._reject(context, params)
            elif action_type == ActionType.FLAG_FOR_REVIEW.value:
                return self._flag_for_review(context, params)
            elif action_type == ActionType.CREATE_NOTIFICATION.value:
                return self._create_notification(context, params)
            elif action_type == ActionType.SEND_WEBHOOK.value:
                return self._send_webhook(context, params)
            elif action_type == ActionType.UPDATE_FIELD.value:
                return self._update_field(context, params)
            elif action_type == ActionType.CREATE_TASK.value:
                return self._create_task(context, params)
            else:
                return {"success": False, "error": f"Unknown action type: {action_type}"}

        except Exception as e:
            logger.error(f"Action execution failed: {e}")
            return {"success": False, "error": str(e)}

    def _auto_approve(self, context: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        """Auto-approve a document."""
        doc_id = context.get("document_id")
        if not doc_id:
            return {"success": False, "error": "No document_id in context"}

        self.db.execute(text("""
            UPDATE perennia_documents
            SET status = 'approved', updated_at = NOW()
            WHERE id = :id AND status NOT IN ('approved', 'rejected')
        """), {"id": doc_id})

        # Log event
        self.db.execute(text("""
            INSERT INTO perennia_document_events (
                document_id, loan_id, event_type, event_data,
                actor_type, created_at
            ) VALUES (
                :doc_id, :loan_id, 'rule_executed',
                :event_data, 'system', NOW()
            )
        """), {
            "doc_id": doc_id,
            "loan_id": context.get("loan_id"),
            "event_data": {"action": "auto_approve", "rule_id": context.get("rule_id")}
        })

        self.db.commit()
        return {"success": True, "action": "auto_approve", "document_id": doc_id}

    def _reject(self, context: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        """Reject a document."""
        doc_id = context.get("document_id")
        reason = params.get("reason", "Rejected by automation rule")

        if not doc_id:
            return {"success": False, "error": "No document_id in context"}

        self.db.execute(text("""
            UPDATE perennia_documents
            SET status = 'rejected', rejection_reason = :reason, updated_at = NOW()
            WHERE id = :id AND status NOT IN ('approved', 'rejected')
        """), {"id": doc_id, "reason": reason})
        self.db.commit()

        return {"success": True, "action": "reject", "document_id": doc_id}

    def _flag_for_review(self, context: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        """Flag document for manual review."""
        doc_id = context.get("document_id")
        flag_reason = params.get("reason", "Flagged by automation rule")

        if not doc_id:
            return {"success": False, "error": "No document_id in context"}

        # Add validation error as flag
        self.db.execute(text("""
            UPDATE perennia_documents
            SET validation_errors = COALESCE(validation_errors, '[]'::jsonb) || :flag,
                updated_at = NOW()
            WHERE id = :id
        """), {"id": doc_id, "flag": [{"type": "review_flag", "reason": flag_reason}]})
        self.db.commit()

        return {"success": True, "action": "flag_for_review", "document_id": doc_id}

    def _create_notification(self, context: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        """Create a notification."""
        template = params.get("template", "rule_notification")
        channel = params.get("channel", "email")
        subject = params.get("subject", "Document Notification")
        body = params.get("body", "A document event has occurred.")

        self.db.execute(text("""
            INSERT INTO perennia_notifications (
                loan_id, lead_id, channel, template,
                subject, body, metadata, status,
                created_at, updated_at
            ) VALUES (
                :loan_id, :lead_id, :channel, :template,
                :subject, :body, :metadata, 'pending',
                NOW(), NOW()
            )
        """), {
            "loan_id": context.get("loan_id"),
            "lead_id": context.get("lead_id"),
            "channel": channel,
            "template": template,
            "subject": subject,
            "body": body,
            "metadata": {
                "rule_id": context.get("rule_id"),
                "document_id": context.get("document_id")
            }
        })
        self.db.commit()

        return {"success": True, "action": "create_notification", "template": template}

    def _send_webhook(self, context: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        """Send webhook to external URL."""
        url = params.get("url")
        if not url:
            return {"success": False, "error": "No webhook URL specified"}

        method = params.get("method", "POST")
        headers = params.get("headers", {})
        headers["Content-Type"] = "application/json"

        payload = {
            "event_type": context.get("event_type"),
            "document_id": context.get("document_id"),
            "loan_id": context.get("loan_id"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "rule_id": context.get("rule_id"),
            "custom_data": params.get("payload", {})
        }

        try:
            response = requests.request(
                method=method,
                url=url,
                json=payload,
                headers=headers,
                timeout=30
            )
            response.raise_for_status()

            return {
                "success": True,
                "action": "send_webhook",
                "url": url,
                "status_code": response.status_code
            }

        except requests.RequestException as e:
            return {"success": False, "error": f"Webhook failed: {str(e)}"}

    def _update_field(self, context: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        """Update a document field."""
        doc_id = context.get("document_id")
        field = params.get("field")
        value = params.get("value")

        if not doc_id or not field:
            return {"success": False, "error": "Missing document_id or field"}

        # Only allow updating specific fields
        allowed_fields = ["doc_subtype", "expiration_date", "document_date"]
        if field not in allowed_fields:
            return {"success": False, "error": f"Field not allowed: {field}"}

        self.db.execute(text(f"""
            UPDATE perennia_documents
            SET {field} = :value, updated_at = NOW()
            WHERE id = :id
        """), {"id": doc_id, "value": value})
        self.db.commit()

        return {"success": True, "action": "update_field", "field": field}

    def _create_task(self, context: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        """Create a follow-up task."""
        # This would integrate with the main task system
        task_type = params.get("task_type", "review")
        description = params.get("description", "Review document")

        # For now, just log the intent
        logger.info(f"Would create task: {task_type} - {description}")

        return {
            "success": True,
            "action": "create_task",
            "task_type": task_type,
            "note": "Task creation not fully implemented"
        }


class PerenniaRulesEngine:
    """
    Rules engine that evaluates and executes document automation rules.

    Triggered by document events, evaluates matching rules, executes actions.
    """

    def __init__(self, db: Session):
        """
        Initialize rules engine.

        Args:
            db: Database session
        """
        self.db = db
        self.evaluator = ConditionEvaluator()
        self.executor = ActionExecutor(db)

    def get_rules_for_trigger(self, trigger: str) -> List[Dict[str, Any]]:
        """Get active rules for a trigger type."""
        result = self.db.execute(text("""
            SELECT id, name, description, trigger, conditions, actions, priority
            FROM perennia_document_rules
            WHERE trigger = :trigger AND is_active = true
            ORDER BY priority ASC
        """), {"trigger": trigger})

        return [dict(row._mapping) for row in result]

    def process_event(
        self,
        event_type: str,
        context: Dict[str, Any]
    ) -> List[RuleResult]:
        """
        Process a document event and execute matching rules.

        Args:
            event_type: Type of event (e.g., 'document_classified')
            context: Event context data

        Returns:
            List of rule execution results
        """
        results = []

        # Get rules for this trigger
        rules = self.get_rules_for_trigger(event_type)

        for rule in rules:
            rule_id = rule['id']
            rule_name = rule['name']

            # Add rule_id to context
            context['rule_id'] = rule_id

            result = RuleResult(
                rule_id=rule_id,
                rule_name=rule_name,
                matched=False,
                actions_executed=[]
            )

            try:
                # Evaluate conditions
                conditions = rule.get('conditions', [])
                if self.evaluator.evaluate(conditions, context):
                    result.matched = True

                    # Execute actions
                    actions = rule.get('actions', [])
                    for action in actions:
                        action_result = self.executor.execute(action, context)
                        if action_result.get('success'):
                            result.actions_executed.append(action.get('type'))
                        else:
                            result.error = action_result.get('error')

                    # Log rule execution
                    self._log_rule_execution(rule_id, context, result)

            except Exception as e:
                logger.error(f"Rule {rule_id} execution failed: {e}")
                result.error = str(e)

            results.append(result)

        return results

    def _log_rule_execution(
        self,
        rule_id: int,
        context: Dict[str, Any],
        result: RuleResult
    ):
        """Log rule execution to events table."""
        self.db.execute(text("""
            INSERT INTO perennia_document_events (
                document_id, loan_id, lead_id,
                event_type, event_data, actor_type, created_at
            ) VALUES (
                :doc_id, :loan_id, :lead_id,
                'rule_executed', :event_data, 'system', NOW()
            )
        """), {
            "doc_id": context.get("document_id"),
            "loan_id": context.get("loan_id"),
            "lead_id": context.get("lead_id"),
            "event_data": {
                "rule_id": rule_id,
                "rule_name": result.rule_name,
                "matched": result.matched,
                "actions_executed": result.actions_executed,
                "error": result.error
            }
        })
        self.db.commit()

    def run_pending_events(self, limit: int = 100) -> Dict[str, Any]:
        """
        Process pending events from the events table.

        This is for batch processing of events that haven't been processed yet.
        """
        # Get unprocessed events
        events = self.db.execute(text("""
            SELECT id, document_id, loan_id, lead_id, request_id,
                   event_type, event_data
            FROM perennia_document_events
            WHERE event_type NOT IN ('rule_executed', 'notification_sent')
              AND event_data->>'rules_processed' IS NULL
            ORDER BY created_at ASC
            LIMIT :limit
        """), {"limit": limit})

        results = {
            "events_processed": 0,
            "rules_matched": 0,
            "actions_executed": 0,
            "details": []
        }

        for row in events:
            event = dict(row._mapping)
            context = {
                "document_id": event.get("document_id"),
                "loan_id": event.get("loan_id"),
                "lead_id": event.get("lead_id"),
                "request_id": event.get("request_id"),
                "event_type": event.get("event_type"),
                **(event.get("event_data") or {})
            }

            rule_results = self.process_event(event["event_type"], context)

            # Mark event as processed
            self.db.execute(text("""
                UPDATE perennia_document_events
                SET event_data = COALESCE(event_data, '{}'::jsonb) || '{"rules_processed": true}'::jsonb
                WHERE id = :id
            """), {"id": event["id"]})
            self.db.commit()

            results["events_processed"] += 1
            for rr in rule_results:
                if rr.matched:
                    results["rules_matched"] += 1
                    results["actions_executed"] += len(rr.actions_executed)

            results["details"].append({
                "event_id": event["id"],
                "event_type": event["event_type"],
                "rules_matched": len([r for r in rule_results if r.matched])
            })

        return results


def run_rules_engine(db: Session, limit: int = 100) -> Dict[str, Any]:
    """
    Run rules engine worker.

    Args:
        db: Database session
        limit: Maximum events to process

    Returns:
        Dict with processing results
    """
    engine = PerenniaRulesEngine(db)
    return engine.run_pending_events(limit)
