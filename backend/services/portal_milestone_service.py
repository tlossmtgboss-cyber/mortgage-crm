"""
Portal Milestone Service - Manages milestone journey for the Perennia Portal.

Handles milestone generation, progress tracking, task management,
and milestone visualization data for the loan journey.
"""

import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, date, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func

from models.portal_models import (
    LifecycleStage, MilestoneStatus, TaskStatus,
    MilestoneTemplate, MilestoneInstance, TaskTemplate, TaskInstance,
    PortalLoan, LoanActivityLog
)

logger = logging.getLogger(__name__)


class PortalMilestoneService:
    """Service for managing milestone journeys."""

    def __init__(self, db: Session):
        self.db = db

    # =========================================================================
    # MILESTONE TEMPLATE MANAGEMENT
    # =========================================================================

    def get_milestone_templates(
        self,
        stage: Optional[LifecycleStage] = None,
        is_active: bool = True,
    ) -> List[Dict[str, Any]]:
        """Get milestone templates, optionally filtered by stage."""
        query = self.db.query(MilestoneTemplate).filter(
            MilestoneTemplate.is_active == is_active
        )

        if stage:
            query = query.filter(MilestoneTemplate.lifecycle_stage == stage)

        templates = query.order_by(
            MilestoneTemplate.lifecycle_stage,
            MilestoneTemplate.order_index
        ).all()

        return [
            {
                "id": t.id,
                "code": t.code,
                "name": t.name,
                "description": t.description,
                "lifecycle_stage": t.lifecycle_stage.value,
                "order_index": t.order_index,
                "icon": t.icon,
                "color": t.color,
                "typical_duration_days": t.typical_duration_days,
                "is_borrower_visible": t.is_borrower_visible,
                "is_partner_visible": t.is_partner_visible,
            }
            for t in templates
        ]

    def create_milestone_template(
        self,
        code: str,
        name: str,
        description: str,
        lifecycle_stage: LifecycleStage,
        order_index: int,
        **kwargs,
    ) -> Dict[str, Any]:
        """Create a new milestone template."""
        template = MilestoneTemplate(
            code=code,
            name=name,
            description=description,
            lifecycle_stage=lifecycle_stage,
            order_index=order_index,
            icon=kwargs.get("icon", "check-circle"),
            color=kwargs.get("color", "#3B82F6"),
            typical_duration_days=kwargs.get("typical_duration_days"),
            is_borrower_visible=kwargs.get("is_borrower_visible", True),
            is_partner_visible=kwargs.get("is_partner_visible", True),
            is_active=True,
        )
        self.db.add(template)
        self.db.commit()
        self.db.refresh(template)

        return {"success": True, "template_id": template.id}

    # =========================================================================
    # MILESTONE INSTANCE MANAGEMENT
    # =========================================================================

    def generate_milestones_for_loan(
        self,
        loan_id: int,
        stage: LifecycleStage,
        expected_close_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """Generate milestone instances for a loan based on templates."""
        # Get templates for this stage
        templates = self.db.query(MilestoneTemplate).filter(
            and_(
                MilestoneTemplate.lifecycle_stage == stage,
                MilestoneTemplate.is_active == True
            )
        ).order_by(MilestoneTemplate.order_index).all()

        if not templates:
            return {
                "success": False,
                "error": f"No milestone templates found for stage {stage.value}",
            }

        # Create milestone instances
        created = []
        cumulative_days = 0

        for template in templates:
            # Calculate target date based on expected close or typical duration
            if expected_close_date and template.typical_duration_days:
                # Work backwards from close date for later milestones
                target_date = expected_close_date - timedelta(
                    days=(len(templates) - template.order_index) * template.typical_duration_days
                )
            elif template.typical_duration_days:
                cumulative_days += template.typical_duration_days
                target_date = date.today() + timedelta(days=cumulative_days)
            else:
                target_date = None

            milestone = MilestoneInstance(
                loan_id=loan_id,
                template_id=template.id,
                status=MilestoneStatus.PENDING,
                target_date=target_date,
                is_visible_to_borrower=template.is_borrower_visible,
                is_visible_to_partner=template.is_partner_visible,
            )
            self.db.add(milestone)
            created.append(template.name)

            # Generate tasks for this milestone
            task_templates = self.db.query(TaskTemplate).filter(
                and_(
                    TaskTemplate.milestone_template_id == template.id,
                    TaskTemplate.is_active == True
                )
            ).order_by(TaskTemplate.order_index).all()

            for task_template in task_templates:
                task = TaskInstance(
                    milestone_id=milestone.id,
                    task_template_id=task_template.id,
                    status=TaskStatus.PENDING,
                    is_visible_to_borrower=task_template.is_borrower_visible,
                )
                self.db.add(task)

        self.db.commit()

        logger.info(f"Generated {len(created)} milestones for loan {loan_id}")

        return {
            "success": True,
            "milestones_created": len(created),
            "milestone_names": created,
        }

    def get_loan_milestones(
        self,
        loan_id: int,
        include_tasks: bool = True,
        borrower_view: bool = False,
    ) -> List[Dict[str, Any]]:
        """Get all milestones for a loan with optional task details."""
        query = self.db.query(MilestoneInstance).filter(
            MilestoneInstance.loan_id == loan_id
        )

        if borrower_view:
            query = query.filter(MilestoneInstance.is_visible_to_borrower == True)

        milestones = query.join(MilestoneTemplate).order_by(
            MilestoneTemplate.lifecycle_stage,
            MilestoneTemplate.order_index
        ).all()

        result = []
        for m in milestones:
            milestone_data = {
                "id": m.id,
                "code": m.template.code,
                "name": m.template.name,
                "description": m.template.description,
                "status": m.status.value,
                "lifecycle_stage": m.template.lifecycle_stage.value,
                "order_index": m.template.order_index,
                "icon": m.template.icon,
                "color": m.template.color,
                "target_date": m.target_date.isoformat() if m.target_date else None,
                "started_at": m.started_at.isoformat() if m.started_at else None,
                "completed_at": m.completed_at.isoformat() if m.completed_at else None,
                "notes": m.notes,
            }

            if include_tasks:
                task_query = self.db.query(TaskInstance).filter(
                    TaskInstance.milestone_id == m.id
                )
                if borrower_view:
                    task_query = task_query.filter(TaskInstance.is_visible_to_borrower == True)

                tasks = task_query.join(TaskTemplate).order_by(
                    TaskTemplate.order_index
                ).all()

                milestone_data["tasks"] = [
                    {
                        "id": t.id,
                        "name": t.task_template.name,
                        "description": t.task_template.description,
                        "status": t.status.value,
                        "is_required": t.task_template.is_required,
                        "is_borrower_action": t.task_template.is_borrower_action,
                        "completed_at": t.completed_at.isoformat() if t.completed_at else None,
                        "completed_by": t.completed_by,
                    }
                    for t in tasks
                ]

            result.append(milestone_data)

        return result

    def get_milestone_progress(self, loan_id: int) -> Dict[str, Any]:
        """Get overall milestone progress for a loan."""
        milestones = self.db.query(MilestoneInstance).filter(
            MilestoneInstance.loan_id == loan_id
        ).all()

        if not milestones:
            return {
                "total": 0,
                "completed": 0,
                "in_progress": 0,
                "pending": 0,
                "progress_percent": 0,
                "current_milestone": None,
            }

        completed = len([m for m in milestones if m.status == MilestoneStatus.COMPLETED])
        in_progress = len([m for m in milestones if m.status == MilestoneStatus.IN_PROGRESS])
        pending = len([m for m in milestones if m.status == MilestoneStatus.PENDING])

        # Find current milestone (first in-progress or first pending)
        current = None
        for m in milestones:
            if m.status == MilestoneStatus.IN_PROGRESS:
                current = {
                    "id": m.id,
                    "name": m.template.name,
                    "status": m.status.value,
                }
                break
        if not current:
            for m in milestones:
                if m.status == MilestoneStatus.PENDING:
                    current = {
                        "id": m.id,
                        "name": m.template.name,
                        "status": m.status.value,
                    }
                    break

        return {
            "total": len(milestones),
            "completed": completed,
            "in_progress": in_progress,
            "pending": pending,
            "progress_percent": round((completed / len(milestones) * 100) if milestones else 0, 1),
            "current_milestone": current,
        }

    def update_milestone_status(
        self,
        milestone_id: int,
        status: MilestoneStatus,
        notes: Optional[str] = None,
        updated_by: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Update milestone status."""
        milestone = self.db.query(MilestoneInstance).filter(
            MilestoneInstance.id == milestone_id
        ).first()

        if not milestone:
            return {"success": False, "error": "Milestone not found"}

        old_status = milestone.status
        milestone.status = status

        if status == MilestoneStatus.IN_PROGRESS and not milestone.started_at:
            milestone.started_at = datetime.utcnow()
        elif status == MilestoneStatus.COMPLETED:
            milestone.completed_at = datetime.utcnow()
            milestone.completed_by = updated_by

        if notes:
            milestone.notes = notes

        # Log activity
        activity = LoanActivityLog(
            loan_id=milestone.loan_id,
            activity_type="milestone_update",
            description=f"Milestone '{milestone.template.name}' changed from {old_status.value} to {status.value}",
            metadata={
                "milestone_id": milestone_id,
                "old_status": old_status.value,
                "new_status": status.value,
            },
            actor=updated_by,
            is_visible_to_borrower=True,
        )
        self.db.add(activity)

        self.db.commit()

        logger.info(f"Milestone {milestone_id} updated to {status.value}")

        return {
            "success": True,
            "milestone_id": milestone_id,
            "old_status": old_status.value,
            "new_status": status.value,
        }

    # =========================================================================
    # TASK MANAGEMENT
    # =========================================================================

    def get_task_details(self, task_id: int) -> Optional[Dict[str, Any]]:
        """Get detailed task information."""
        task = self.db.query(TaskInstance).filter(
            TaskInstance.id == task_id
        ).first()

        if not task:
            return None

        return {
            "id": task.id,
            "name": task.task_template.name,
            "description": task.task_template.description,
            "milestone_id": task.milestone_id,
            "milestone_name": task.milestone.template.name,
            "status": task.status.value,
            "is_required": task.task_template.is_required,
            "is_borrower_action": task.task_template.is_borrower_action,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            "completed_by": task.completed_by,
            "metadata": task.metadata,
        }

    def update_task_status(
        self,
        task_id: int,
        status: TaskStatus,
        completed_by: Optional[str] = None,
        metadata: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Update task status."""
        task = self.db.query(TaskInstance).filter(
            TaskInstance.id == task_id
        ).first()

        if not task:
            return {"success": False, "error": "Task not found"}

        old_status = task.status
        task.status = status

        if status == TaskStatus.COMPLETED:
            task.completed_at = datetime.utcnow()
            task.completed_by = completed_by

        if metadata:
            task.metadata = {**(task.metadata or {}), **metadata}

        # Check if all tasks in milestone are complete
        milestone = task.milestone
        all_tasks = self.db.query(TaskInstance).filter(
            TaskInstance.milestone_id == milestone.id
        ).all()

        required_tasks_complete = all(
            t.status == TaskStatus.COMPLETED
            for t in all_tasks
            if t.task_template.is_required
        )

        # Auto-advance milestone if all required tasks complete
        if required_tasks_complete and milestone.status != MilestoneStatus.COMPLETED:
            milestone.status = MilestoneStatus.COMPLETED
            milestone.completed_at = datetime.utcnow()

            # Log milestone completion
            activity = LoanActivityLog(
                loan_id=milestone.loan_id,
                activity_type="milestone_completed",
                description=f"Milestone '{milestone.template.name}' completed",
                metadata={"milestone_id": milestone.id},
                actor=completed_by,
                is_visible_to_borrower=True,
            )
            self.db.add(activity)

        self.db.commit()

        return {
            "success": True,
            "task_id": task_id,
            "old_status": old_status.value,
            "new_status": status.value,
            "milestone_auto_completed": required_tasks_complete and milestone.status == MilestoneStatus.COMPLETED,
        }

    def get_pending_borrower_tasks(self, loan_id: int) -> List[Dict[str, Any]]:
        """Get tasks requiring borrower action."""
        tasks = self.db.query(TaskInstance).join(TaskTemplate).join(MilestoneInstance).filter(
            and_(
                MilestoneInstance.loan_id == loan_id,
                TaskTemplate.is_borrower_action == True,
                TaskInstance.status.in_([TaskStatus.PENDING, TaskStatus.IN_PROGRESS]),
                TaskInstance.is_visible_to_borrower == True
            )
        ).all()

        return [
            {
                "id": t.id,
                "name": t.task_template.name,
                "description": t.task_template.description,
                "milestone_name": t.milestone.template.name,
                "status": t.status.value,
                "is_required": t.task_template.is_required,
            }
            for t in tasks
        ]

    # =========================================================================
    # VISUALIZATION DATA
    # =========================================================================

    def get_timeline_data(
        self,
        loan_id: int,
        view_type: str = "horizontal",
        borrower_view: bool = False,
    ) -> Dict[str, Any]:
        """Get milestone data formatted for timeline visualization."""
        milestones = self.get_loan_milestones(
            loan_id=loan_id,
            include_tasks=True,
            borrower_view=borrower_view,
        )

        progress = self.get_milestone_progress(loan_id)

        # Group milestones by lifecycle stage
        by_stage = {}
        for m in milestones:
            stage = m["lifecycle_stage"]
            if stage not in by_stage:
                by_stage[stage] = []
            by_stage[stage].append(m)

        return {
            "view_type": view_type,
            "loan_id": loan_id,
            "progress": progress,
            "milestones": milestones,
            "by_stage": by_stage,
            "stage_order": [
                "PREAPPROVAL", "UNDER_CONTRACT", "PROCESSING",
                "CLEAR_TO_CLOSE", "FUNDED", "MUM"
            ],
        }

    def get_journey_summary(self, loan_id: int) -> Dict[str, Any]:
        """Get journey summary for dashboard display."""
        progress = self.get_milestone_progress(loan_id)
        pending_tasks = self.get_pending_borrower_tasks(loan_id)

        # Get next upcoming milestone
        next_milestone = self.db.query(MilestoneInstance).join(MilestoneTemplate).filter(
            and_(
                MilestoneInstance.loan_id == loan_id,
                MilestoneInstance.status.in_([MilestoneStatus.PENDING, MilestoneStatus.IN_PROGRESS])
            )
        ).order_by(MilestoneTemplate.order_index).first()

        return {
            "progress": progress,
            "pending_borrower_tasks": len(pending_tasks),
            "borrower_tasks": pending_tasks[:3],  # Top 3 tasks
            "next_milestone": {
                "id": next_milestone.id,
                "name": next_milestone.template.name,
                "target_date": next_milestone.target_date.isoformat() if next_milestone and next_milestone.target_date else None,
            } if next_milestone else None,
        }
