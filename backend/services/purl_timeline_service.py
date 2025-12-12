"""
PURL Timeline Service

Provides business logic for PURL timeline operations including:
- Milestone tracking and updates
- Timeline event aggregation
- Task management for borrowers
- SLA monitoring
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_

from models.purl import (
    PURLWorkspace,
    PURLLoan,
    PURLLoanMilestone,
    PURLMilestoneDefinition,
    PURLTask,
    PURLAuditLog,
    PURLEventsOutbox,
    MilestoneStatus,
    TaskStatus,
    TaskPriority,
    EventStatus
)

logger = logging.getLogger(__name__)


class PURLTimelineService:
    """
    Service for PURL timeline operations.
    Manages milestones, tasks, and timeline events.
    """

    def __init__(self, db: Session):
        self.db = db

    # =========================================================================
    # TIMELINE RETRIEVAL
    # =========================================================================

    def get_workspace_timeline(
        self,
        organization_id: int,
        workspace_id: int
    ) -> Dict[str, Any]:
        """
        Get complete timeline with milestones and events.

        Returns:
            Dict with milestones and events lists
        """
        # Get current active loan
        loan = self.db.query(PURLLoan).filter(
            PURLLoan.workspace_id == workspace_id,
            PURLLoan.status.in_(['active', 'processing', 'underwriting', 'closing'])
        ).order_by(PURLLoan.created_at.desc()).first()

        milestones = []
        if loan:
            milestones = self._get_loan_milestones(loan.id)

        # Get timeline events from audit log
        events = self._get_timeline_events(workspace_id)

        return {
            "milestones": milestones,
            "events": events,
            "loan_status": loan.status if loan else None,
            "current_stage": self._get_current_stage(milestones) if milestones else "lead"
        }

    def _get_loan_milestones(self, loan_id: int) -> List[Dict[str, Any]]:
        """Get milestones for a loan."""
        milestones = self.db.query(PURLLoanMilestone).join(
            PURLMilestoneDefinition
        ).filter(
            PURLLoanMilestone.loan_id == loan_id
        ).order_by(PURLMilestoneDefinition.order_index).all()

        result = []
        for m in milestones:
            definition = m.definition

            # Calculate if overdue
            is_overdue = False
            if m.due_at and m.status in [MilestoneStatus.PENDING.value, MilestoneStatus.IN_PROGRESS.value]:
                is_overdue = m.due_at < datetime.now(timezone.utc)

            result.append({
                "id": m.id,
                "code": definition.code,
                "display_name": definition.display_name,
                "description": definition.description,
                "stage": definition.stage,
                "order_index": definition.order_index,
                "status": m.status,
                "due_at": m.due_at.isoformat() if m.due_at else None,
                "started_at": m.started_at.isoformat() if m.started_at else None,
                "completed_at": m.completed_at.isoformat() if m.completed_at else None,
                "delay_reason": m.delay_reason,
                "is_overdue": is_overdue,
                "sla_days": definition.sla_days,
                "sla_type": definition.sla_type
            })

        return result

    def _get_timeline_events(
        self,
        workspace_id: int,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get timeline events from audit log."""
        # Filter to meaningful events for timeline
        timeline_actions = [
            'workspace_created',
            'contact_added',
            'application_started',
            'application_submitted',
            'document_uploaded',
            'document_verified',
            'task_completed',
            'milestone_completed',
            'message_sent'
        ]

        events = self.db.query(PURLAuditLog).filter(
            PURLAuditLog.workspace_id == workspace_id,
            PURLAuditLog.action.in_(timeline_actions)
        ).order_by(PURLAuditLog.created_at.desc()).limit(limit).all()

        result = []
        for e in events:
            # Format event for display
            title, description = self._format_event(e.action, e.metadata)

            result.append({
                "id": e.id,
                "event_type": e.action,
                "title": title,
                "description": description,
                "timestamp": e.created_at.isoformat() if e.created_at else None,
                "actor_type": e.actor_type,
                "actor_id": e.actor_id,
                "metadata": e.metadata
            })

        return result

    def _format_event(
        self,
        action: str,
        metadata: Dict[str, Any]
    ) -> Tuple[str, str]:
        """Format event action into human-readable title and description."""
        titles = {
            "workspace_created": "Workspace Created",
            "contact_added": "Contact Added",
            "application_started": "Application Started",
            "application_submitted": "Application Submitted",
            "document_uploaded": "Document Uploaded",
            "document_verified": "Document Verified",
            "task_completed": "Task Completed",
            "milestone_completed": "Milestone Completed",
            "message_sent": "New Message"
        }

        descriptions = {
            "workspace_created": "Your loan workspace has been created.",
            "contact_added": "A new contact has been added to your loan.",
            "application_started": "Loan application has been started.",
            "application_submitted": "Your application has been submitted for review.",
            "document_uploaded": f"Document uploaded: {metadata.get('file_name', 'Unknown')}",
            "document_verified": f"Document verified: {metadata.get('doc_type', 'Unknown')}",
            "task_completed": f"Task completed: {metadata.get('title', 'Unknown')}",
            "milestone_completed": f"Milestone reached: {metadata.get('display_name', 'Unknown')}",
            "message_sent": "You have a new message from your loan team."
        }

        return titles.get(action, action), descriptions.get(action, "")

    def _get_current_stage(self, milestones: List[Dict[str, Any]]) -> str:
        """Determine current stage from milestones."""
        if not milestones:
            return "lead"

        # Find the last completed milestone
        completed = [m for m in milestones if m["status"] == MilestoneStatus.COMPLETED.value]

        if not completed:
            return milestones[0]["stage"] if milestones else "application"

        # Return stage of last completed milestone
        return completed[-1]["stage"]

    # =========================================================================
    # MILESTONE MANAGEMENT
    # =========================================================================

    def update_milestone_status(
        self,
        milestone_id: int,
        new_status: MilestoneStatus,
        completion_notes: Optional[str] = None,
        delay_reason: Optional[str] = None
    ) -> bool:
        """
        Update milestone status.

        Returns:
            True if successful
        """
        milestone = self.db.query(PURLLoanMilestone).filter(
            PURLLoanMilestone.id == milestone_id
        ).first()

        if not milestone:
            return False

        old_status = milestone.status
        now = datetime.now(timezone.utc)

        milestone.status = new_status.value

        if new_status == MilestoneStatus.IN_PROGRESS:
            milestone.started_at = now
        elif new_status == MilestoneStatus.COMPLETED:
            milestone.completed_at = now
            milestone.completion_notes = completion_notes
        elif new_status == MilestoneStatus.DELAYED:
            milestone.delay_reason = delay_reason

        self.db.commit()

        # Get definition for event
        definition = milestone.definition

        # Emit event
        self._emit_event(
            organization_id=milestone.organization_id,
            workspace_id=None,  # Get from loan
            loan_id=milestone.loan_id,
            event_key=f"milestone_{new_status.value}",
            payload={
                "milestone_id": milestone_id,
                "code": definition.code,
                "display_name": definition.display_name,
                "old_status": old_status,
                "new_status": new_status.value
            }
        )

        logger.info(f"Milestone {milestone_id} status: {old_status} -> {new_status.value}")
        return True

    def get_overdue_milestones(
        self,
        organization_id: int,
        workspace_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Get overdue milestones."""
        query = self.db.query(PURLLoanMilestone).join(
            PURLMilestoneDefinition
        ).filter(
            PURLLoanMilestone.organization_id == organization_id,
            PURLLoanMilestone.status.in_([
                MilestoneStatus.PENDING.value,
                MilestoneStatus.IN_PROGRESS.value
            ]),
            PURLLoanMilestone.due_at < datetime.now(timezone.utc)
        )

        if workspace_id:
            query = query.join(PURLLoan).filter(
                PURLLoan.workspace_id == workspace_id
            )

        milestones = query.order_by(PURLLoanMilestone.due_at).all()

        return [
            {
                "id": m.id,
                "loan_id": m.loan_id,
                "code": m.definition.code,
                "display_name": m.definition.display_name,
                "due_at": m.due_at.isoformat() if m.due_at else None,
                "days_overdue": (datetime.now(timezone.utc) - m.due_at).days if m.due_at else 0
            }
            for m in milestones
        ]

    # =========================================================================
    # TASK MANAGEMENT
    # =========================================================================

    def get_borrower_tasks(
        self,
        organization_id: int,
        workspace_id: int,
        contact_id: Optional[int] = None,
        include_completed: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Get tasks for borrower.

        Args:
            organization_id: Organization ID
            workspace_id: Workspace ID
            contact_id: Filter to specific contact
            include_completed: Whether to include completed tasks

        Returns:
            List of task dicts
        """
        query = self.db.query(PURLTask).filter(
            PURLTask.organization_id == organization_id,
            PURLTask.workspace_id == workspace_id
        )

        if not include_completed:
            query = query.filter(
                PURLTask.status.in_([TaskStatus.OPEN.value, TaskStatus.IN_PROGRESS.value])
            )

        if contact_id:
            query = query.filter(
                or_(
                    PURLTask.assigned_to_contact_id == contact_id,
                    PURLTask.assigned_to_contact_id.is_(None)
                )
            )

        tasks = query.order_by(
            # Priority order
            func.case(
                (PURLTask.priority == TaskPriority.URGENT.value, 1),
                (PURLTask.priority == TaskPriority.HIGH.value, 2),
                (PURLTask.priority == TaskPriority.MEDIUM.value, 3),
                (PURLTask.priority == TaskPriority.LOW.value, 4),
                else_=5
            ),
            PURLTask.due_at.asc().nullslast(),
            PURLTask.created_at.desc()
        ).all()

        return [self._task_to_dict(t) for t in tasks]

    def create_task(
        self,
        organization_id: int,
        workspace_id: int,
        title: str,
        description: Optional[str] = None,
        task_type: str = "general",
        priority: TaskPriority = TaskPriority.MEDIUM,
        due_at: Optional[datetime] = None,
        assigned_to_contact_id: Optional[int] = None,
        assigned_to_user_id: Optional[int] = None,
        loan_id: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        Create a new task.

        Returns:
            Task ID
        """
        task = PURLTask(
            organization_id=organization_id,
            workspace_id=workspace_id,
            loan_id=loan_id,
            title=title,
            description=description,
            task_type=task_type,
            status=TaskStatus.OPEN.value,
            priority=priority.value,
            assigned_to_contact_id=assigned_to_contact_id,
            assigned_to_user_id=assigned_to_user_id,
            due_at=due_at,
            metadata=metadata or {}
        )

        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)

        # Emit event
        self._emit_event(
            organization_id=organization_id,
            workspace_id=workspace_id,
            loan_id=loan_id,
            event_key="task_created",
            payload={
                "task_id": task.id,
                "title": title,
                "priority": priority.value,
                "assigned_to_contact_id": assigned_to_contact_id
            }
        )

        logger.info(f"Created task {task.id} for workspace {workspace_id}")
        return task.id

    def complete_task(
        self,
        organization_id: int,
        workspace_id: int,
        task_id: int,
        completed_by_contact_id: Optional[int] = None,
        completed_by_user_id: Optional[int] = None
    ) -> bool:
        """
        Mark a task as completed.

        Returns:
            True if successful
        """
        task = self.db.query(PURLTask).filter(
            PURLTask.id == task_id,
            PURLTask.organization_id == organization_id,
            PURLTask.workspace_id == workspace_id
        ).first()

        if not task:
            return False

        if task.status == TaskStatus.COMPLETED.value:
            return True  # Already completed

        task.status = TaskStatus.COMPLETED.value
        task.completed_at = datetime.now(timezone.utc)
        task.completed_by_contact_id = completed_by_contact_id
        task.completed_by_user_id = completed_by_user_id

        self.db.commit()

        # Emit event
        self._emit_event(
            organization_id=organization_id,
            workspace_id=workspace_id,
            loan_id=task.loan_id,
            event_key="task_completed",
            payload={
                "task_id": task_id,
                "title": task.title,
                "completed_by_contact_id": completed_by_contact_id
            }
        )

        logger.info(f"Completed task {task_id}")
        return True

    def update_task(
        self,
        task_id: int,
        updates: Dict[str, Any]
    ) -> Optional[PURLTask]:
        """Update task fields."""
        task = self.db.query(PURLTask).filter(
            PURLTask.id == task_id
        ).first()

        if not task:
            return None

        allowed_fields = [
            "title", "description", "status", "priority",
            "due_at", "assigned_to_user_id", "assigned_to_contact_id"
        ]

        for field in allowed_fields:
            if field in updates and updates[field] is not None:
                setattr(task, field, updates[field])

        self.db.commit()
        self.db.refresh(task)

        return task

    # =========================================================================
    # SLA MONITORING
    # =========================================================================

    def get_sla_summary(
        self,
        organization_id: int,
        workspace_id: Optional[int] = None,
        loan_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Get SLA summary for milestones.

        Returns:
            Dict with SLA statistics
        """
        query = self.db.query(PURLLoanMilestone).filter(
            PURLLoanMilestone.organization_id == organization_id
        )

        if workspace_id:
            query = query.join(PURLLoan).filter(
                PURLLoan.workspace_id == workspace_id
            )

        if loan_id:
            query = query.filter(PURLLoanMilestone.loan_id == loan_id)

        milestones = query.all()

        if not milestones:
            return {"total": 0, "on_track": 0, "at_risk": 0, "overdue": 0}

        now = datetime.now(timezone.utc)
        on_track = 0
        at_risk = 0
        overdue = 0
        completed = 0

        for m in milestones:
            if m.status == MilestoneStatus.COMPLETED.value:
                completed += 1
            elif m.due_at:
                if m.due_at < now:
                    overdue += 1
                elif m.due_at < now + timedelta(days=2):
                    at_risk += 1
                else:
                    on_track += 1
            else:
                on_track += 1

        return {
            "total": len(milestones),
            "completed": completed,
            "on_track": on_track,
            "at_risk": at_risk,
            "overdue": overdue,
            "completion_rate": round((completed / len(milestones)) * 100, 1) if milestones else 0
        }

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _task_to_dict(self, task: PURLTask) -> Dict[str, Any]:
        """Convert task to dict."""
        is_overdue = False
        if task.due_at and task.status in [TaskStatus.OPEN.value, TaskStatus.IN_PROGRESS.value]:
            is_overdue = task.due_at < datetime.now(timezone.utc)

        return {
            "id": task.id,
            "organization_id": task.organization_id,
            "workspace_id": task.workspace_id,
            "loan_id": task.loan_id,
            "title": task.title,
            "description": task.description,
            "task_type": task.task_type,
            "status": task.status,
            "priority": task.priority,
            "assigned_to_user_id": task.assigned_to_user_id,
            "assigned_to_contact_id": task.assigned_to_contact_id,
            "due_at": task.due_at.isoformat() if task.due_at else None,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            "is_overdue": is_overdue,
            "metadata": task.metadata,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "updated_at": task.updated_at.isoformat() if task.updated_at else None
        }

    def _emit_event(
        self,
        organization_id: int,
        workspace_id: Optional[int],
        event_key: str,
        payload: Dict[str, Any],
        loan_id: Optional[int] = None
    ):
        """Emit event to outbox."""
        event = PURLEventsOutbox(
            organization_id=organization_id,
            workspace_id=workspace_id,
            loan_id=loan_id,
            event_key=event_key,
            payload=payload,
            status=EventStatus.PENDING.value
        )
        self.db.add(event)
