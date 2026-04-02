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

from sqlalchemy.exc import SQLAlchemyError
from models.portal_models import (
    LifecycleStage, MilestoneStatus, TaskStatus, PortalUserRole,
    MilestoneTemplate, MilestoneInstance, TaskTemplate, TaskInstance,
    PortalLoan, LoanActivityLog
)

logger = logging.getLogger(__name__)


class PortalMilestoneService:
    """Service for managing milestone journeys."""

    def __init__(self, db: Session):
        self.db = db

    def _resolve_loan_id(self, loan_id: int) -> int:
        """Resolve crm_deal_id to portal_loan.id."""
        try:
            # First try to find by portal_loan.id
            portal_loan = self.db.query(PortalLoan).filter(
                PortalLoan.id == loan_id
            ).first()

            if portal_loan:
                return portal_loan.id

            # Try by crm_deal_id
            portal_loan = self.db.query(PortalLoan).filter(
                PortalLoan.crm_deal_id == loan_id
            ).first()

            if portal_loan:
                return portal_loan.id
        except SQLAlchemyError as e:
            logger.warning(f"Could not resolve loan_id {loan_id}: {e}")
            self.db.rollback()

        # Return original if not found (will return empty results)
        return loan_id

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
            query = query.filter(MilestoneTemplate.stage == stage)

        templates = query.order_by(
            MilestoneTemplate.stage,
            MilestoneTemplate.display_order
        ).all()

        return [
            {
                "id": t.id,
                "key": t.key,
                "name": t.name,
                "description": t.description,
                "stage": t.stage.value if t.stage else None,
                "display_order": t.display_order,
                "icon": t.icon,
                "color_code": t.color_code,
                "visible_to_borrower": t.visible_to_borrower,
                "visible_to_partner": t.visible_to_partner,
            }
            for t in templates
        ]

    def create_milestone_template(
        self,
        key: str,
        name: str,
        description: str,
        stage: LifecycleStage,
        display_order: int,
        **kwargs,
    ) -> Dict[str, Any]:
        """Create a new milestone template."""
        template = MilestoneTemplate(
            key=key,
            name=name,
            description=description,
            stage=stage,
            display_order=display_order,
            icon=kwargs.get("icon", "check-circle"),
            color_code=kwargs.get("color_code", "#3B82F6"),
            visible_to_borrower=kwargs.get("visible_to_borrower", True),
            visible_to_partner=kwargs.get("visible_to_partner", True),
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
                MilestoneTemplate.stage == stage,
                MilestoneTemplate.is_active == True
            )
        ).order_by(MilestoneTemplate.display_order).all()

        if not templates:
            return {
                "success": False,
                "error": f"No milestone templates found for stage {stage.value}",
            }

        # Create milestone instances
        created = []
        cumulative_days = 0

        for i, template in enumerate(templates):
            # Calculate due date based on expected close or SLA duration
            if expected_close_date and template.sla_duration:
                # Work backwards from close date for later milestones
                due = expected_close_date - timedelta(
                    days=(len(templates) - i) * (template.sla_duration or 3)
                )
            elif template.sla_duration:
                cumulative_days += template.sla_duration
                due = date.today() + timedelta(days=cumulative_days)
            else:
                due = None

            milestone = MilestoneInstance(
                loan_id=loan_id,
                template_id=template.id,
                status=MilestoneStatus.LOCKED if i > 0 else MilestoneStatus.ACTIVE,
                due_date=due,
            )
            self.db.add(milestone)
            self.db.flush()  # Get the milestone ID
            created.append(template.name)

            # Generate tasks for this milestone
            task_templates = self.db.query(TaskTemplate).filter(
                and_(
                    TaskTemplate.milestone_template_id == template.id,
                )
            ).order_by(TaskTemplate.display_order).all()

            for task_template in task_templates:
                task = TaskInstance(
                    milestone_instance_id=milestone.id,
                    template_id=task_template.id,
                    title=task_template.title,
                    instructions=task_template.instructions,
                    owner_role=task_template.owner_role,
                    status=TaskStatus.TODO,
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
        try:
            resolved_loan_id = self._resolve_loan_id(loan_id)
            query = self.db.query(MilestoneInstance).filter(
                MilestoneInstance.loan_id == resolved_loan_id
            )

            if borrower_view:
                query = query.join(MilestoneTemplate).filter(
                    MilestoneTemplate.visible_to_borrower == True
                )

            milestones = query.join(MilestoneTemplate).order_by(
                MilestoneTemplate.stage,
                MilestoneTemplate.display_order
            ).all()
        except SQLAlchemyError as e:
            logger.warning(f"Could not get milestones for loan {loan_id}: {e}")
            self.db.rollback()
            return []

        result = []
        for m in milestones:
            milestone_data = {
                "id": m.id,
                "key": m.template.key,
                "name": m.template.name,
                "description": m.template.description,
                "status": m.status.value if m.status else None,
                "stage": m.template.stage.value if m.template.stage else None,
                "display_order": m.template.display_order,
                "icon": m.template.icon,
                "color_code": m.template.color_code,
                "due_date": m.due_date.isoformat() if m.due_date else None,
                "entered_at": m.entered_at.isoformat() if m.entered_at else None,
                "completed_at": m.completed_at.isoformat() if m.completed_at else None,
                "notes": m.notes,
            }

            if include_tasks:
                tasks = self.db.query(TaskInstance).filter(
                    TaskInstance.milestone_instance_id == m.id
                ).all()

                # For borrower view, only show tasks owned by borrower
                if borrower_view:
                    tasks = [t for t in tasks if t.owner_role == PortalUserRole.BORROWER]

                milestone_data["tasks"] = [
                    {
                        "id": t.id,
                        "title": t.title,
                        "instructions": t.instructions,
                        "status": t.status.value if t.status else None,
                        "owner_role": t.owner_role.value if t.owner_role else None,
                        "is_borrower_task": t.owner_role == PortalUserRole.BORROWER,
                        "completed_at": t.completed_at.isoformat() if t.completed_at else None,
                        "completed_by": t.completed_by,
                    }
                    for t in tasks
                ]

            result.append(milestone_data)

        return result

    def get_milestone_progress(self, loan_id: int) -> Dict[str, Any]:
        """Get overall milestone progress for a loan."""
        try:
            resolved_loan_id = self._resolve_loan_id(loan_id)
            milestones = self.db.query(MilestoneInstance).filter(
                MilestoneInstance.loan_id == resolved_loan_id
            ).all()
        except SQLAlchemyError as e:
            logger.warning(f"Could not get milestones for loan {loan_id}: {e}")
            self.db.rollback()
            milestones = []

        if not milestones:
            return {
                "total": 0,
                "completed": 0,
                "in_progress": 0,
                "pending": 0,
                "progress_percent": 0,
                "current_milestone": None,
            }

        completed = len([m for m in milestones if m.status == MilestoneStatus.COMPLETE])
        active = len([m for m in milestones if m.status == MilestoneStatus.ACTIVE])
        locked = len([m for m in milestones if m.status == MilestoneStatus.LOCKED])

        # Find current milestone (first active or first locked if none active)
        current = None
        for m in milestones:
            if m.status == MilestoneStatus.ACTIVE:
                current = {
                    "id": m.id,
                    "name": m.template.name,
                    "status": m.status.value,
                }
                break
        if not current:
            for m in milestones:
                if m.status == MilestoneStatus.LOCKED:
                    current = {
                        "id": m.id,
                        "name": m.template.name,
                        "status": m.status.value,
                    }
                    break

        return {
            "total": len(milestones),
            "completed": completed,
            "in_progress": active,
            "pending": locked,
            "progress_percent": round((completed / len(milestones) * 100) if milestones else 0, 1),
            "current_milestone": current,
        }

    def update_milestone_status(
        self,
        milestone_id: int,
        status: MilestoneStatus,
        notes: Optional[str] = None,
        updated_by: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Update milestone status."""
        milestone = self.db.query(MilestoneInstance).filter(
            MilestoneInstance.id == milestone_id
        ).first()

        if not milestone:
            return {"success": False, "error": "Milestone not found"}

        old_status = milestone.status
        milestone.status = status

        if status == MilestoneStatus.ACTIVE and not milestone.entered_at:
            milestone.entered_at = datetime.now(timezone.utc)
        elif status == MilestoneStatus.COMPLETED:
            milestone.completed_at = datetime.now(timezone.utc)

        if notes:
            milestone.notes = notes

        # Log activity
        activity = LoanActivityLog(
            loan_id=milestone.loan_id,
            activity_type="milestone_update",
            activity_title=f"Milestone Updated: {milestone.template.name}",
            activity_description=f"Milestone '{milestone.template.name}' changed from {old_status.value} to {status.value}",
            extra_data={
                "milestone_id": milestone_id,
                "old_status": old_status.value,
                "new_status": status.value,
            },
            actor_id=updated_by,
            visible_to_borrower=True,
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
            "title": task.title,
            "instructions": task.instructions,
            "milestone_id": task.milestone_instance_id,
            "milestone_name": task.milestone.template.name if task.milestone and task.milestone.template else None,
            "status": task.status.value if task.status else None,
            "owner_role": task.owner_role.value if task.owner_role else None,
            "is_borrower_task": task.owner_role == PortalUserRole.BORROWER,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            "completed_by": task.completed_by,
            "notes": task.notes,
        }

    def update_task_status(
        self,
        task_id: int,
        status: TaskStatus,
        completed_by: Optional[int] = None,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Update task status."""
        task = self.db.query(TaskInstance).filter(
            TaskInstance.id == task_id
        ).first()

        if not task:
            return {"success": False, "error": "Task not found"}

        old_status = task.status
        task.status = status

        if status == TaskStatus.DONE:
            task.completed_at = datetime.now(timezone.utc)
            task.completed_by = completed_by

        if notes:
            task.notes = notes

        # Check if all tasks in milestone are complete
        milestone = task.milestone
        all_tasks = self.db.query(TaskInstance).filter(
            TaskInstance.milestone_instance_id == milestone.id
        ).all()

        # Get required tasks from templates
        all_required_complete = True
        for t in all_tasks:
            if t.template_id:
                template = self.db.query(TaskTemplate).filter(
                    TaskTemplate.id == t.template_id
                ).first()
                if template and template.is_required and t.status != TaskStatus.DONE:
                    all_required_complete = False
                    break
            elif t.status != TaskStatus.DONE:
                # If no template, assume required
                all_required_complete = False
                break

        # Auto-advance milestone if all required tasks complete
        milestone_auto_completed = False
        if all_required_complete and milestone.status != MilestoneStatus.COMPLETED:
            milestone.status = MilestoneStatus.COMPLETED
            milestone.completed_at = datetime.now(timezone.utc)
            milestone_auto_completed = True

            # Log milestone completion
            activity = LoanActivityLog(
                loan_id=milestone.loan_id,
                activity_type="milestone_completed",
                activity_title=f"Milestone Completed: {milestone.template.name}",
                activity_description=f"Milestone '{milestone.template.name}' completed",
                extra_data={"milestone_id": milestone.id},
                actor_id=completed_by,
                visible_to_borrower=True,
            )
            self.db.add(activity)

        self.db.commit()

        return {
            "success": True,
            "task_id": task_id,
            "old_status": old_status.value if old_status else None,
            "new_status": status.value,
            "milestone_auto_completed": milestone_auto_completed,
        }

    def get_pending_borrower_tasks(self, loan_id: int) -> List[Dict[str, Any]]:
        """Get tasks requiring borrower action."""
        try:
            resolved_loan_id = self._resolve_loan_id(loan_id)
            tasks = self.db.query(TaskInstance).join(MilestoneInstance).filter(
                and_(
                    MilestoneInstance.loan_id == resolved_loan_id,
                    TaskInstance.owner_role == PortalUserRole.BORROWER,
                    TaskInstance.status.in_([TaskStatus.TODO, TaskStatus.IN_PROGRESS]),
                )
            ).all()

            return [
                {
                    "id": t.id,
                    "title": t.title,
                    "instructions": t.instructions,
                    "milestone_name": t.milestone.template.name if t.milestone and t.milestone.template else None,
                    "status": t.status.value if t.status else None,
                }
                for t in tasks
            ]
        except Exception as e:
            logger.warning(f"Could not get pending borrower tasks for loan {loan_id}: {e}")
            self.db.rollback()
            return []

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
            stage = m["stage"]
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
        resolved_loan_id = self._resolve_loan_id(loan_id)
        progress = self.get_milestone_progress(loan_id)
        pending_tasks = self.get_pending_borrower_tasks(loan_id)

        # Get next upcoming milestone
        next_milestone = self.db.query(MilestoneInstance).join(MilestoneTemplate).filter(
            and_(
                MilestoneInstance.loan_id == resolved_loan_id,
                MilestoneInstance.status.in_([MilestoneStatus.LOCKED, MilestoneStatus.ACTIVE])
            )
        ).order_by(MilestoneTemplate.display_order).first()

        return {
            "progress": progress,
            "pending_borrower_tasks": len(pending_tasks),
            "borrower_tasks": pending_tasks[:3],  # Top 3 tasks
            "next_milestone": {
                "id": next_milestone.id,
                "name": next_milestone.template.name,
                "due_date": next_milestone.due_date.isoformat() if next_milestone and next_milestone.due_date else None,
            } if next_milestone else None,
        }
