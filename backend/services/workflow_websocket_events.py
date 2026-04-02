"""
Workflow WebSocket Events

Real-time notifications for workflow events using the existing WebSocket infrastructure.
Provides notifications for:
- Task scheduled/due/completed
- Workflow status changes
- AI confidence evaluations
- Escalation alerts
"""

import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class WorkflowEvent:
    """Helper class for creating standardized workflow event messages"""

    # =========================================================================
    # TASK EVENTS
    # =========================================================================

    @staticmethod
    def task_scheduled(
        task_instance_id: int,
        task_name: str,
        task_type: str,
        scheduled_date: str,
        lead_id: Optional[int] = None,
        loan_id: Optional[int] = None,
        contact_name: Optional[str] = None
    ) -> dict:
        """New task has been scheduled."""
        return {
            "type": "workflow_task_scheduled",
            "task_instance_id": task_instance_id,
            "task_name": task_name,
            "task_type": task_type,
            "scheduled_date": scheduled_date,
            "lead_id": lead_id,
            "loan_id": loan_id,
            "contact_name": contact_name,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    @staticmethod
    def task_due(
        task_instance_id: int,
        task_name: str,
        task_type: str,
        lead_id: Optional[int] = None,
        loan_id: Optional[int] = None,
        contact_name: Optional[str] = None,
        contact_phone: Optional[str] = None,
        route: Optional[str] = None
    ) -> dict:
        """Task is now due and ready for action."""
        return {
            "type": "workflow_task_due",
            "task_instance_id": task_instance_id,
            "task_name": task_name,
            "task_type": task_type,
            "lead_id": lead_id,
            "loan_id": loan_id,
            "contact_name": contact_name,
            "contact_phone": contact_phone,
            "route": route,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    @staticmethod
    def task_completed(
        task_instance_id: int,
        task_name: str,
        completion_source: str,
        contact_made: bool = False,
        siblings_cancelled: int = 0,
        lead_id: Optional[int] = None,
        loan_id: Optional[int] = None
    ) -> dict:
        """Task has been completed."""
        return {
            "type": "workflow_task_completed",
            "task_instance_id": task_instance_id,
            "task_name": task_name,
            "completion_source": completion_source,
            "contact_made": contact_made,
            "siblings_cancelled": siblings_cancelled,
            "lead_id": lead_id,
            "loan_id": loan_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    @staticmethod
    def task_failed(
        task_instance_id: int,
        task_name: str,
        error: str,
        lead_id: Optional[int] = None,
        loan_id: Optional[int] = None
    ) -> dict:
        """Task execution failed."""
        return {
            "type": "workflow_task_failed",
            "task_instance_id": task_instance_id,
            "task_name": task_name,
            "error": error,
            "lead_id": lead_id,
            "loan_id": loan_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    @staticmethod
    def task_skipped(
        task_instance_id: int,
        task_name: str,
        reason: str,
        lead_id: Optional[int] = None,
        loan_id: Optional[int] = None
    ) -> dict:
        """Task has been skipped."""
        return {
            "type": "workflow_task_skipped",
            "task_instance_id": task_instance_id,
            "task_name": task_name,
            "reason": reason,
            "lead_id": lead_id,
            "loan_id": loan_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    @staticmethod
    def task_overdue(
        task_instance_id: int,
        task_name: str,
        due_date: str,
        days_overdue: int,
        lead_id: Optional[int] = None,
        loan_id: Optional[int] = None,
        contact_name: Optional[str] = None
    ) -> dict:
        """Task is overdue and needs attention."""
        return {
            "type": "workflow_task_overdue",
            "task_instance_id": task_instance_id,
            "task_name": task_name,
            "due_date": due_date,
            "days_overdue": days_overdue,
            "lead_id": lead_id,
            "loan_id": loan_id,
            "contact_name": contact_name,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    # =========================================================================
    # WORKFLOW EVENTS
    # =========================================================================

    @staticmethod
    def workflow_enrolled(
        instance_id: int,
        workflow_key: str,
        workflow_name: str,
        lead_id: Optional[int] = None,
        loan_id: Optional[int] = None,
        contact_name: Optional[str] = None
    ) -> dict:
        """Entity enrolled in a workflow."""
        return {
            "type": "workflow_enrolled",
            "instance_id": instance_id,
            "workflow_key": workflow_key,
            "workflow_name": workflow_name,
            "lead_id": lead_id,
            "loan_id": loan_id,
            "contact_name": contact_name,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    @staticmethod
    def workflow_paused(
        instance_id: int,
        workflow_name: str,
        reason: Optional[str] = None,
        lead_id: Optional[int] = None,
        loan_id: Optional[int] = None
    ) -> dict:
        """Workflow has been paused."""
        return {
            "type": "workflow_paused",
            "instance_id": instance_id,
            "workflow_name": workflow_name,
            "reason": reason,
            "lead_id": lead_id,
            "loan_id": loan_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    @staticmethod
    def workflow_resumed(
        instance_id: int,
        workflow_name: str,
        lead_id: Optional[int] = None,
        loan_id: Optional[int] = None
    ) -> dict:
        """Workflow has been resumed."""
        return {
            "type": "workflow_resumed",
            "instance_id": instance_id,
            "workflow_name": workflow_name,
            "lead_id": lead_id,
            "loan_id": loan_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    @staticmethod
    def workflow_completed(
        instance_id: int,
        workflow_name: str,
        tasks_completed: int,
        tasks_skipped: int,
        duration_days: int,
        lead_id: Optional[int] = None,
        loan_id: Optional[int] = None
    ) -> dict:
        """Workflow has been completed."""
        return {
            "type": "workflow_completed",
            "instance_id": instance_id,
            "workflow_name": workflow_name,
            "tasks_completed": tasks_completed,
            "tasks_skipped": tasks_skipped,
            "duration_days": duration_days,
            "lead_id": lead_id,
            "loan_id": loan_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    @staticmethod
    def workflow_cancelled(
        instance_id: int,
        workflow_name: str,
        reason: str,
        lead_id: Optional[int] = None,
        loan_id: Optional[int] = None
    ) -> dict:
        """Workflow has been cancelled."""
        return {
            "type": "workflow_cancelled",
            "instance_id": instance_id,
            "workflow_name": workflow_name,
            "reason": reason,
            "lead_id": lead_id,
            "loan_id": loan_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    # =========================================================================
    # AI CONFIDENCE EVENTS
    # =========================================================================

    @staticmethod
    def ai_evaluation_complete(
        task_instance_id: int,
        task_name: str,
        confidence_score: float,
        recommendation: str,
        auto_executed: bool = False,
        lead_id: Optional[int] = None,
        loan_id: Optional[int] = None
    ) -> dict:
        """AI confidence evaluation completed."""
        return {
            "type": "ai_evaluation_complete",
            "task_instance_id": task_instance_id,
            "task_name": task_name,
            "confidence_score": confidence_score,
            "recommendation": recommendation,
            "auto_executed": auto_executed,
            "lead_id": lead_id,
            "loan_id": loan_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    @staticmethod
    def ai_task_executing(
        task_instance_id: int,
        task_name: str,
        task_type: str,
        lead_id: Optional[int] = None,
        loan_id: Optional[int] = None,
        contact_name: Optional[str] = None
    ) -> dict:
        """AI is executing a task autonomously."""
        return {
            "type": "ai_task_executing",
            "task_instance_id": task_instance_id,
            "task_name": task_name,
            "task_type": task_type,
            "lead_id": lead_id,
            "loan_id": loan_id,
            "contact_name": contact_name,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    @staticmethod
    def ai_task_executed(
        task_instance_id: int,
        task_name: str,
        task_type: str,
        success: bool,
        result_summary: Optional[str] = None,
        error: Optional[str] = None,
        lead_id: Optional[int] = None,
        loan_id: Optional[int] = None
    ) -> dict:
        """AI task execution completed."""
        return {
            "type": "ai_task_executed",
            "task_instance_id": task_instance_id,
            "task_name": task_name,
            "task_type": task_type,
            "success": success,
            "result_summary": result_summary,
            "error": error,
            "lead_id": lead_id,
            "loan_id": loan_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    @staticmethod
    def ai_review_required(
        task_instance_id: int,
        task_name: str,
        confidence_score: float,
        reason: str,
        lead_id: Optional[int] = None,
        loan_id: Optional[int] = None,
        contact_name: Optional[str] = None
    ) -> dict:
        """Task requires human review before AI execution."""
        return {
            "type": "ai_review_required",
            "task_instance_id": task_instance_id,
            "task_name": task_name,
            "confidence_score": confidence_score,
            "reason": reason,
            "lead_id": lead_id,
            "loan_id": loan_id,
            "contact_name": contact_name,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    # =========================================================================
    # ESCALATION EVENTS
    # =========================================================================

    @staticmethod
    def escalation_created(
        task_instance_id: int,
        task_name: str,
        escalation_reason: str,
        escalated_to_user_id: int,
        escalated_to_name: str,
        lead_id: Optional[int] = None,
        loan_id: Optional[int] = None
    ) -> dict:
        """Task has been escalated."""
        return {
            "type": "escalation_created",
            "task_instance_id": task_instance_id,
            "task_name": task_name,
            "escalation_reason": escalation_reason,
            "escalated_to_user_id": escalated_to_user_id,
            "escalated_to_name": escalated_to_name,
            "lead_id": lead_id,
            "loan_id": loan_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    @staticmethod
    def sla_breach_warning(
        task_instance_id: int,
        task_name: str,
        sla_name: str,
        hours_remaining: float,
        lead_id: Optional[int] = None,
        loan_id: Optional[int] = None,
        contact_name: Optional[str] = None
    ) -> dict:
        """SLA breach warning - task nearing deadline."""
        return {
            "type": "sla_breach_warning",
            "task_instance_id": task_instance_id,
            "task_name": task_name,
            "sla_name": sla_name,
            "hours_remaining": hours_remaining,
            "lead_id": lead_id,
            "loan_id": loan_id,
            "contact_name": contact_name,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    @staticmethod
    def sla_breach(
        task_instance_id: int,
        task_name: str,
        sla_name: str,
        hours_overdue: float,
        lead_id: Optional[int] = None,
        loan_id: Optional[int] = None,
        contact_name: Optional[str] = None
    ) -> dict:
        """SLA has been breached."""
        return {
            "type": "sla_breach",
            "task_instance_id": task_instance_id,
            "task_name": task_name,
            "sla_name": sla_name,
            "hours_overdue": hours_overdue,
            "lead_id": lead_id,
            "loan_id": loan_id,
            "contact_name": contact_name,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    # =========================================================================
    # DIALER INTEGRATION EVENTS
    # =========================================================================

    @staticmethod
    def dialer_task_queued(
        task_instance_id: int,
        task_name: str,
        dialer_session_id: int,
        position: int,
        contact_name: str,
        contact_phone: str
    ) -> dict:
        """Workflow task added to dialer queue."""
        return {
            "type": "workflow_dialer_task_queued",
            "task_instance_id": task_instance_id,
            "task_name": task_name,
            "dialer_session_id": dialer_session_id,
            "position": position,
            "contact_name": contact_name,
            "contact_phone": contact_phone,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    @staticmethod
    def dialer_call_outcome(
        task_instance_id: int,
        task_name: str,
        call_status: str,
        call_duration: Optional[int] = None,
        contact_made: bool = False,
        siblings_cancelled: int = 0,
        lead_id: Optional[int] = None,
        loan_id: Optional[int] = None
    ) -> dict:
        """Dialer call outcome for workflow task."""
        return {
            "type": "workflow_dialer_call_outcome",
            "task_instance_id": task_instance_id,
            "task_name": task_name,
            "call_status": call_status,
            "call_duration": call_duration,
            "contact_made": contact_made,
            "siblings_cancelled": siblings_cancelled,
            "lead_id": lead_id,
            "loan_id": loan_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }


class WorkflowWebSocketNotifier:
    """
    Sends workflow events via WebSocket.

    Uses the existing ws_manager singleton from telephony/websocket.py
    """

    def __init__(self):
        self._ws_manager = None

    @property
    def ws_manager(self):
        """Lazy load WebSocket manager to avoid circular imports."""
        if self._ws_manager is None:
            try:
                from telephony.websocket import ws_manager
                self._ws_manager = ws_manager
            except ImportError:
                logger.warning("WebSocket manager not available")
                self._ws_manager = None
        return self._ws_manager

    async def notify_user(self, user_id: int, event: dict):
        """Send event to a specific user."""
        if self.ws_manager:
            await self.ws_manager.send_to_agent(str(user_id), event)
        else:
            logger.debug(f"WebSocket not available, skipping notification: {event.get('type')}")

    def notify_user_sync(self, user_id: int, event: dict):
        """Synchronous version for non-async contexts."""
        if self.ws_manager:
            self.ws_manager.send_to_agent_sync(str(user_id), event)
        else:
            logger.debug(f"WebSocket not available, skipping notification: {event.get('type')}")

    async def notify_users(self, user_ids: List[int], event: dict):
        """Send event to multiple users."""
        for user_id in user_ids:
            await self.notify_user(user_id, event)

    async def broadcast(self, event: dict):
        """Broadcast event to all connected users."""
        if self.ws_manager:
            await self.ws_manager.broadcast_to_all(event)

    # =========================================================================
    # CONVENIENCE METHODS
    # =========================================================================

    async def notify_task_scheduled(
        self,
        user_id: int,
        task_instance_id: int,
        task_name: str,
        task_type: str,
        scheduled_date: str,
        **kwargs
    ):
        """Notify user of newly scheduled task."""
        event = WorkflowEvent.task_scheduled(
            task_instance_id=task_instance_id,
            task_name=task_name,
            task_type=task_type,
            scheduled_date=scheduled_date,
            **kwargs
        )
        await self.notify_user(user_id, event)

    async def notify_task_due(
        self,
        user_id: int,
        task_instance_id: int,
        task_name: str,
        task_type: str,
        **kwargs
    ):
        """Notify user of task that is now due."""
        event = WorkflowEvent.task_due(
            task_instance_id=task_instance_id,
            task_name=task_name,
            task_type=task_type,
            **kwargs
        )
        await self.notify_user(user_id, event)

    async def notify_task_completed(
        self,
        user_id: int,
        task_instance_id: int,
        task_name: str,
        completion_source: str,
        **kwargs
    ):
        """Notify user of task completion."""
        event = WorkflowEvent.task_completed(
            task_instance_id=task_instance_id,
            task_name=task_name,
            completion_source=completion_source,
            **kwargs
        )
        await self.notify_user(user_id, event)

    async def notify_ai_evaluation(
        self,
        user_id: int,
        task_instance_id: int,
        task_name: str,
        confidence_score: float,
        recommendation: str,
        **kwargs
    ):
        """Notify user of AI evaluation result."""
        event = WorkflowEvent.ai_evaluation_complete(
            task_instance_id=task_instance_id,
            task_name=task_name,
            confidence_score=confidence_score,
            recommendation=recommendation,
            **kwargs
        )
        await self.notify_user(user_id, event)

    async def notify_escalation(
        self,
        user_id: int,
        task_instance_id: int,
        task_name: str,
        escalation_reason: str,
        escalated_to_user_id: int,
        escalated_to_name: str,
        **kwargs
    ):
        """Notify user of task escalation."""
        event = WorkflowEvent.escalation_created(
            task_instance_id=task_instance_id,
            task_name=task_name,
            escalation_reason=escalation_reason,
            escalated_to_user_id=escalated_to_user_id,
            escalated_to_name=escalated_to_name,
            **kwargs
        )
        # Notify both the escalated-to user and the original assignee
        await self.notify_user(escalated_to_user_id, event)
        if user_id != escalated_to_user_id:
            await self.notify_user(user_id, event)


# Singleton instance
workflow_notifier = WorkflowWebSocketNotifier()


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def get_workflow_notifier() -> WorkflowWebSocketNotifier:
    """Get the workflow notifier singleton."""
    return workflow_notifier
