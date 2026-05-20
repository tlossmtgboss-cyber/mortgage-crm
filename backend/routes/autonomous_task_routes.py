"""
Autonomous Task Routes

REST API for managing autonomous AI agent tasks — view, configure,
enable/disable, and manually trigger the proactive agent scheduler.

Endpoints:
    GET  /api/v1/autonomous/tasks                   List all autonomous tasks
    POST /api/v1/autonomous/tasks                   Create a new task (admin)
    PUT  /api/v1/autonomous/tasks/{task_id}          Update task config (admin)
    POST /api/v1/autonomous/tasks/{task_id}/toggle   Enable/disable task (admin)
    POST /api/v1/autonomous/tasks/{task_id}/trigger  Manually trigger task (admin)
    GET  /api/v1/autonomous/tasks/{task_id}/executions  Execution history
    GET  /api/v1/autonomous/executions/{execution_id}/actions  Actions from execution
    GET  /api/v1/autonomous/actions/pending           List pending approval actions
    POST /api/v1/autonomous/actions/{action_id}/approve  Approve a pending action
    POST /api/v1/autonomous/actions/{action_id}/reject   Reject a pending action
    GET  /api/v1/autonomous/confidence               Confidence graduation dashboard
    GET  /api/v1/autonomous/dashboard                Autonomous agents dashboard
    POST /api/v1/autonomous/tasks/seed               Seed default tasks (admin)
    GET  /api/v1/autonomous/circuits                 Circuit breaker status (admin)
    POST /api/v1/autonomous/circuits/{org_id}/{agent_type}/reset  Reset circuit (admin)
"""

from datetime import datetime, timezone, timedelta
from typing import Optional, List

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, Integer
from sqlalchemy.orm import Session
import logging

logger = logging.getLogger(__name__)

KNOWN_AGENT_TYPES = {
    "lead_nurturing",
    "compliance_watchdog",
    "pipeline_monitor",
    "document_followup",
    "rate_alert",
    "lead_scoring",
    "reporting",
    "client_lifecycle",
    "client_audit",
}

DEFAULT_TASKS = [
    {
        "agent_type": "lead_nurturing",
        "task_name": "Daily stale-lead outreach",
        "description": "Identifies leads with no activity in 48+ hours and queues nurture touches.",
        "schedule_cron": "0 8 * * *",
        "priority": 3,
        "config": {"stale_threshold_hours": 48, "max_leads_per_run": 50},
    },
    {
        "agent_type": "compliance_watchdog",
        "task_name": "Compliance document expiry check",
        "description": "Scans active loans for expiring or missing compliance documents.",
        "schedule_cron": "0 7 * * *",
        "priority": 1,
        "config": {"expiry_warning_days": 14},
    },
    {
        "agent_type": "pipeline_monitor",
        "task_name": "Pipeline health snapshot",
        "description": "Evaluates pipeline velocity, flags stalled loans, generates alerts.",
        "schedule_cron": "0 9 * * *",
        "priority": 4,
        "config": {"stall_threshold_days": 5},
    },
    {
        "agent_type": "document_followup",
        "task_name": "Missing-document follow-up",
        "description": "Sends reminders to borrowers with outstanding document requests.",
        "schedule_cron": "0 10 * * *",
        "priority": 3,
        "config": {"reminder_interval_hours": 72, "max_reminders": 3},
    },
    {
        "agent_type": "rate_alert",
        "task_name": "Rate movement alerts",
        "description": "Monitors rate changes and notifies LOs with float-down opportunities.",
        "schedule_interval_minutes": 60,
        "priority": 2,
        "config": {"rate_change_threshold_bps": 12.5},
    },
    {
        "agent_type": "lead_scoring",
        "task_name": "Nightly lead re-scoring",
        "description": "Re-evaluates lead scores based on recent activity and engagement signals.",
        "schedule_cron": "0 2 * * *",
        "priority": 5,
        "config": {"min_data_points": 3},
    },
    {
        "agent_type": "reporting",
        "task_name": "Weekly performance digest",
        "description": "Compiles weekly KPI digest for LOs and managers.",
        "schedule_cron": "0 6 * * 1",
        "priority": 7,
        "config": {"include_team_comparison": True},
    },
    {
        "agent_type": "client_lifecycle",
        "task_name": "Post-closing lifecycle check",
        "description": "Monitors funded loans for refinance timing, anniversary touches, and referral opportunities.",
        "schedule_cron": "0 9 * * *",
        "priority": 6,
        "config": {"refi_rate_drop_bps": 50, "anniversary_months": [6, 12]},
    },
]


# ---------------------------------------------------------------------------
# Pydantic request / response models
# ---------------------------------------------------------------------------

class TaskCreateRequest(BaseModel):
    agent_type: str = Field(..., max_length=100)
    task_name: str = Field(..., max_length=255)
    description: Optional[str] = None
    schedule_cron: Optional[str] = None
    schedule_interval_minutes: Optional[int] = Field(default=None, ge=1)
    config: Optional[dict] = None
    priority: Optional[int] = Field(default=5, ge=1, le=10)


class TaskUpdateRequest(BaseModel):
    task_name: Optional[str] = Field(default=None, max_length=255)
    description: Optional[str] = None
    schedule_cron: Optional[str] = None
    schedule_interval_minutes: Optional[int] = Field(default=None, ge=1)
    config: Optional[dict] = None
    priority: Optional[int] = Field(default=None, ge=1, le=10)
    max_retries: Optional[int] = Field(default=None, ge=0, le=10)
    timeout_seconds: Optional[int] = Field(default=None, ge=30, le=3600)


class TaskToggleRequest(BaseModel):
    is_enabled: bool


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------

def register_autonomous_task_routes(app, get_db, get_current_user, **kwargs):
    """
    Register autonomous task management routes.

    Args:
        app: FastAPI application instance.
        get_db: Database session dependency.
        get_current_user: Auth dependency returning current User.
    """

    # Lazy imports to avoid circular deps
    from database.models.autonomous_task import (
        AutonomousTask,
        TaskExecution,
        AgentAction,
    )

    def _require_admin(current_user):
        """Raise 403 if the user is not a platform or site admin."""
        role = getattr(current_user, "role", None)
        if role not in ("Platform Admin", "Site Admin", "platform_admin", "site_admin"):
            raise HTTPException(status_code=403, detail="Admin access required")

    def _task_to_dict(t):
        """Serialize an AutonomousTask row to a dict."""
        return {
            "id": t.id,
            "organization_id": t.organization_id,
            "agent_type": t.agent_type,
            "task_name": t.task_name,
            "description": t.description,
            "schedule_cron": t.schedule_cron,
            "schedule_interval_minutes": t.schedule_interval_minutes,
            "is_enabled": t.is_enabled,
            "priority": t.priority,
            "config": t.config,
            "last_run_at": t.last_run_at.isoformat() if t.last_run_at else None,
            "next_run_at": t.next_run_at.isoformat() if t.next_run_at else None,
            "last_run_status": t.last_run_status,
            "consecutive_failures": t.consecutive_failures,
            "max_retries": t.max_retries,
            "timeout_seconds": t.timeout_seconds,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "updated_at": t.updated_at.isoformat() if t.updated_at else None,
        }

    def _execution_to_dict(ex):
        """Serialize a TaskExecution row to a dict."""
        return {
            "id": ex.id,
            "task_id": ex.task_id,
            "status": ex.status,
            "trigger": ex.trigger,
            "started_at": ex.started_at.isoformat() if ex.started_at else None,
            "completed_at": ex.completed_at.isoformat() if ex.completed_at else None,
            "duration_seconds": float(ex.duration_seconds) if ex.duration_seconds else None,
            "items_processed": ex.items_processed,
            "items_acted_on": ex.items_acted_on,
            "actions_taken": ex.actions_taken,
            "result_summary": ex.result_summary,
            "errors": ex.errors,
            "metrics": ex.metrics,
            "created_at": ex.created_at.isoformat() if ex.created_at else None,
        }

    def _action_to_dict(a):
        """Serialize an AgentAction row to a dict."""
        return {
            "id": a.id,
            "execution_id": a.execution_id,
            "action_type": a.action_type,
            "target_entity": a.target_entity,
            "target_id": a.target_id,
            "description": a.description,
            "payload": a.payload,
            "status": a.status,
            "requires_approval": a.requires_approval,
            "approved_by": a.approved_by,
            "approved_at": a.approved_at.isoformat() if a.approved_at else None,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }

    # -------------------------------------------------------------------
    # GET /api/v1/autonomous/tasks - List all autonomous tasks
    # -------------------------------------------------------------------
    @app.get("/api/v1/autonomous/tasks", tags=["Autonomous Tasks"])
    async def list_autonomous_tasks(
        agent_type: Optional[str] = Query(default=None),
        is_enabled: Optional[bool] = Query(default=None),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """List all autonomous tasks for the current organization."""
        try:
            q = db.query(AutonomousTask).filter(
                AutonomousTask.organization_id == current_user.organization_id,
            )
            if agent_type:
                q = q.filter(AutonomousTask.agent_type == agent_type)
            if is_enabled is not None:
                q = q.filter(AutonomousTask.is_enabled == is_enabled)

            tasks = q.order_by(AutonomousTask.priority.asc(), AutonomousTask.task_name.asc()).all()
            return {"tasks": [_task_to_dict(t) for t in tasks], "total": len(tasks)}

        except Exception as e:
            logger.exception(f"Failed to list autonomous tasks: {e}")
            raise HTTPException(status_code=500, detail="Failed to list autonomous tasks")

    # -------------------------------------------------------------------
    # POST /api/v1/autonomous/tasks - Create a new task (admin)
    # -------------------------------------------------------------------
    @app.post("/api/v1/autonomous/tasks", tags=["Autonomous Tasks"])
    async def create_autonomous_task(
        body: TaskCreateRequest,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """Create a new autonomous task. Admin only."""
        _require_admin(current_user)

        if body.agent_type not in KNOWN_AGENT_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown agent_type '{body.agent_type}'. Must be one of: {sorted(KNOWN_AGENT_TYPES)}",
            )

        if not body.schedule_cron and not body.schedule_interval_minutes:
            raise HTTPException(
                status_code=400,
                detail="Either schedule_cron or schedule_interval_minutes is required",
            )

        try:
            task = AutonomousTask(
                organization_id=current_user.organization_id,
                agent_type=body.agent_type,
                task_name=body.task_name,
                description=body.description,
                schedule_cron=body.schedule_cron,
                schedule_interval_minutes=body.schedule_interval_minutes,
                config=body.config,
                priority=body.priority or 5,
                created_by=current_user.id,
            )
            db.add(task)
            db.commit()
            db.refresh(task)
            return _task_to_dict(task)

        except HTTPException:
            raise
        except Exception as e:
            db.rollback()
            logger.exception(f"Failed to create autonomous task: {e}")
            raise HTTPException(status_code=500, detail="Failed to create autonomous task")

    # -------------------------------------------------------------------
    # PUT /api/v1/autonomous/tasks/{task_id} - Update task config (admin)
    # -------------------------------------------------------------------
    @app.put("/api/v1/autonomous/tasks/{task_id}", tags=["Autonomous Tasks"])
    async def update_autonomous_task(
        task_id: int,
        body: TaskUpdateRequest,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """Update an autonomous task configuration. Admin only."""
        _require_admin(current_user)

        try:
            task = db.query(AutonomousTask).filter(
                AutonomousTask.id == task_id,
                AutonomousTask.organization_id == current_user.organization_id,
            ).first()

            if not task:
                raise HTTPException(status_code=404, detail="Task not found")

            update_data = body.dict(exclude_unset=True)
            for field, value in update_data.items():
                setattr(task, field, value)

            db.commit()
            db.refresh(task)
            return _task_to_dict(task)

        except HTTPException:
            raise
        except Exception as e:
            db.rollback()
            logger.exception(f"Failed to update autonomous task {task_id}: {e}")
            raise HTTPException(status_code=500, detail="Failed to update autonomous task")

    # -------------------------------------------------------------------
    # POST /api/v1/autonomous/tasks/{task_id}/toggle - Enable/disable (admin)
    # -------------------------------------------------------------------
    @app.post("/api/v1/autonomous/tasks/{task_id}/toggle", tags=["Autonomous Tasks"])
    async def toggle_autonomous_task(
        task_id: int,
        body: TaskToggleRequest,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """Enable or disable an autonomous task. Admin only."""
        _require_admin(current_user)

        try:
            task = db.query(AutonomousTask).filter(
                AutonomousTask.id == task_id,
                AutonomousTask.organization_id == current_user.organization_id,
            ).first()

            if not task:
                raise HTTPException(status_code=404, detail="Task not found")

            task.is_enabled = body.is_enabled
            if not body.is_enabled:
                task.next_run_at = None
            db.commit()
            db.refresh(task)

            action = "enabled" if body.is_enabled else "disabled"
            logger.info(f"Autonomous task {task_id} ({task.agent_type}) {action} by user {current_user.id}")
            return {"status": action, "task": _task_to_dict(task)}

        except HTTPException:
            raise
        except Exception as e:
            db.rollback()
            logger.exception(f"Failed to toggle autonomous task {task_id}: {e}")
            raise HTTPException(status_code=500, detail="Failed to toggle autonomous task")

    # -------------------------------------------------------------------
    # POST /api/v1/autonomous/tasks/{task_id}/trigger - Manual trigger (admin)
    # -------------------------------------------------------------------
    @app.post("/api/v1/autonomous/tasks/{task_id}/trigger", tags=["Autonomous Tasks"])
    async def trigger_autonomous_task(
        task_id: int,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """Manually trigger an autonomous task to run immediately. Admin only."""
        _require_admin(current_user)

        try:
            task = db.query(AutonomousTask).filter(
                AutonomousTask.id == task_id,
                AutonomousTask.organization_id == current_user.organization_id,
            ).first()

            if not task:
                raise HTTPException(status_code=404, detail="Task not found")

            # Create execution record
            now = datetime.now(timezone.utc)
            execution = TaskExecution(
                task_id=task.id,
                organization_id=current_user.organization_id,
                status="running",
                started_at=now,
                trigger="manual",
            )
            db.add(execution)
            db.flush()

            # Run the agent
            items_processed = 0
            items_acted_on = 0
            errors = []
            result_summary = None

            try:
                from services.autonomous_task_runner import run_autonomous_agent
                result = await run_autonomous_agent(
                    agent_type=task.agent_type,
                    config=task.config or {},
                    organization_id=current_user.organization_id,
                    execution_id=execution.id,
                    db=db,
                )
                items_processed = result.get("items_processed", 0)
                items_acted_on = result.get("items_acted_on", 0)
                result_summary = result.get("summary", "Completed successfully")
                execution.status = "completed"
            except ImportError:
                # Runner service not yet implemented — record a stub execution
                result_summary = "Agent runner not yet implemented. Execution recorded as placeholder."
                execution.status = "completed"
                logger.warning(f"autonomous_task_runner not available for agent_type={task.agent_type}")
            except Exception as run_err:
                errors.append(str(run_err))
                execution.status = "failed"
                result_summary = f"Execution failed: {run_err}"
                logger.exception(f"Autonomous task {task_id} execution failed: {run_err}")

            completed_at = datetime.now(timezone.utc)
            duration = (completed_at - now).total_seconds()

            execution.completed_at = completed_at
            execution.duration_seconds = duration
            execution.items_processed = items_processed
            execution.items_acted_on = items_acted_on
            execution.result_summary = result_summary
            execution.errors = errors if errors else None

            # Update task run tracking
            task.last_run_at = now
            task.last_run_status = execution.status
            if execution.status == "failed":
                task.consecutive_failures = (task.consecutive_failures or 0) + 1
            else:
                task.consecutive_failures = 0

            db.commit()
            db.refresh(execution)

            return {
                "execution": _execution_to_dict(execution),
                "task": _task_to_dict(task),
            }

        except HTTPException:
            raise
        except Exception as e:
            db.rollback()
            logger.exception(f"Failed to trigger autonomous task {task_id}: {e}")
            raise HTTPException(status_code=500, detail="Failed to trigger autonomous task")

    # -------------------------------------------------------------------
    # GET /api/v1/autonomous/tasks/{task_id}/executions - Execution history
    # -------------------------------------------------------------------
    @app.get("/api/v1/autonomous/tasks/{task_id}/executions", tags=["Autonomous Tasks"])
    async def get_task_executions(
        task_id: int,
        limit: int = Query(default=20, ge=1, le=100),
        status: Optional[str] = Query(default=None),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """Get execution history for a specific autonomous task."""
        try:
            # Verify task belongs to org
            task = db.query(AutonomousTask).filter(
                AutonomousTask.id == task_id,
                AutonomousTask.organization_id == current_user.organization_id,
            ).first()

            if not task:
                raise HTTPException(status_code=404, detail="Task not found")

            q = db.query(TaskExecution).filter(
                TaskExecution.task_id == task_id,
                TaskExecution.organization_id == current_user.organization_id,
            )
            if status:
                q = q.filter(TaskExecution.status == status)

            total = q.count()
            executions = (
                q.order_by(TaskExecution.started_at.desc())
                .limit(limit)
                .all()
            )

            return {
                "task_id": task_id,
                "task_name": task.task_name,
                "total": total,
                "limit": limit,
                "executions": [_execution_to_dict(ex) for ex in executions],
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.exception(f"Failed to fetch executions for task {task_id}: {e}")
            raise HTTPException(status_code=500, detail="Failed to fetch task executions")

    # -------------------------------------------------------------------
    # GET /api/v1/autonomous/executions/{execution_id}/actions - Actions
    # -------------------------------------------------------------------
    @app.get("/api/v1/autonomous/executions/{execution_id}/actions", tags=["Autonomous Tasks"])
    async def get_execution_actions(
        execution_id: int,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """Get all actions from a specific task execution."""
        try:
            execution = db.query(TaskExecution).filter(
                TaskExecution.id == execution_id,
                TaskExecution.organization_id == current_user.organization_id,
            ).first()

            if not execution:
                raise HTTPException(status_code=404, detail="Execution not found")

            actions = (
                db.query(AgentAction)
                .filter(AgentAction.execution_id == execution_id)
                .order_by(AgentAction.created_at.asc())
                .all()
            )

            return {
                "execution_id": execution_id,
                "task_id": execution.task_id,
                "status": execution.status,
                "total": len(actions),
                "actions": [_action_to_dict(a) for a in actions],
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.exception(f"Failed to fetch actions for execution {execution_id}: {e}")
            raise HTTPException(status_code=500, detail="Failed to fetch execution actions")

    # -------------------------------------------------------------------
    # GET /api/v1/autonomous/dashboard - Autonomous agents dashboard
    # -------------------------------------------------------------------
    @app.get("/api/v1/autonomous/dashboard", tags=["Autonomous Tasks"])
    async def autonomous_dashboard(
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """Dashboard summary of autonomous agent activity."""
        try:
            org_id = current_user.organization_id

            # Task counts
            total_tasks = db.query(AutonomousTask).filter(
                AutonomousTask.organization_id == org_id,
            ).count()
            enabled_tasks = db.query(AutonomousTask).filter(
                AutonomousTask.organization_id == org_id,
                AutonomousTask.is_enabled == True,
            ).count()

            # Last 24h executions
            cutoff_24h = datetime.now(timezone.utc) - timedelta(hours=24)
            last_24h_q = db.query(TaskExecution).filter(
                TaskExecution.organization_id == org_id,
                TaskExecution.started_at >= cutoff_24h,
            )
            last_24h_executions = last_24h_q.count()
            last_24h_completed = last_24h_q.filter(
                TaskExecution.status == "completed"
            ).count()
            success_rate = round(last_24h_completed / last_24h_executions * 100, 1) if last_24h_executions > 0 else 0.0

            # Breakdown by agent type
            type_rows = (
                db.query(
                    AutonomousTask.agent_type,
                    func.count().label("task_count"),
                    func.sum(func.cast(AutonomousTask.is_enabled, Integer)).label("enabled_count"),
                )
                .filter(AutonomousTask.organization_id == org_id)
                .group_by(AutonomousTask.agent_type)
                .all()
            )
            by_agent_type = {}
            for agent_type, task_count, enabled_count in type_rows:
                # Get last execution for this agent type
                last_exec = (
                    db.query(TaskExecution)
                    .join(AutonomousTask, TaskExecution.task_id == AutonomousTask.id)
                    .filter(
                        AutonomousTask.organization_id == org_id,
                        AutonomousTask.agent_type == agent_type,
                    )
                    .order_by(TaskExecution.started_at.desc())
                    .first()
                )
                by_agent_type[agent_type] = {
                    "task_count": task_count,
                    "enabled_count": int(enabled_count or 0),
                    "last_execution": _execution_to_dict(last_exec) if last_exec else None,
                }

            # Recent actions (last 50)
            recent_actions = (
                db.query(AgentAction)
                .filter(AgentAction.organization_id == org_id)
                .order_by(AgentAction.created_at.desc())
                .limit(50)
                .all()
            )

            return {
                "total_tasks": total_tasks,
                "enabled_tasks": enabled_tasks,
                "last_24h_executions": last_24h_executions,
                "success_rate": success_rate,
                "by_agent_type": by_agent_type,
                "recent_actions": [_action_to_dict(a) for a in recent_actions],
            }

        except Exception as e:
            logger.exception(f"Failed to build autonomous dashboard: {e}")
            raise HTTPException(status_code=500, detail="Failed to build autonomous dashboard")

    # -------------------------------------------------------------------
    # POST /api/v1/autonomous/tasks/seed - Seed default tasks (admin)
    # -------------------------------------------------------------------
    @app.post("/api/v1/autonomous/tasks/seed", tags=["Autonomous Tasks"])
    async def seed_default_tasks(
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """Seed default autonomous tasks for the organization. Admin only.
        Skips if tasks already exist for this org."""
        _require_admin(current_user)

        try:
            org_id = current_user.organization_id

            existing_count = db.query(AutonomousTask).filter(
                AutonomousTask.organization_id == org_id,
            ).count()

            if existing_count > 0:
                return {
                    "status": "skipped",
                    "message": f"Organization already has {existing_count} autonomous tasks",
                    "existing_count": existing_count,
                }

            created = []
            for task_def in DEFAULT_TASKS:
                task = AutonomousTask(
                    organization_id=org_id,
                    agent_type=task_def["agent_type"],
                    task_name=task_def["task_name"],
                    description=task_def.get("description"),
                    schedule_cron=task_def.get("schedule_cron"),
                    schedule_interval_minutes=task_def.get("schedule_interval_minutes"),
                    priority=task_def.get("priority", 5),
                    config=task_def.get("config"),
                    is_enabled=False,  # seeded tasks start disabled
                    created_by=current_user.id,
                )
                db.add(task)
                created.append(task_def["task_name"])

            db.commit()

            return {
                "status": "seeded",
                "message": f"Created {len(created)} default autonomous tasks (all disabled)",
                "tasks_created": created,
            }

        except HTTPException:
            raise
        except Exception as e:
            db.rollback()
            logger.exception(f"Failed to seed default autonomous tasks: {e}")
            raise HTTPException(status_code=500, detail="Failed to seed default tasks")

    # -------------------------------------------------------------------
    # GET /api/v1/autonomous/actions/pending — List pending approval actions
    # -------------------------------------------------------------------
    @app.get("/api/v1/autonomous/actions/pending", tags=["Autonomous Tasks"])
    async def list_pending_actions(
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
        action_type: Optional[str] = Query(default=None),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """List all pending-approval agent actions for the current organization."""
        try:
            q = db.query(AgentAction).filter(
                AgentAction.organization_id == current_user.organization_id,
                AgentAction.status == "pending_approval",
            )
            if action_type:
                q = q.filter(AgentAction.action_type == action_type)

            total = q.count()
            actions = (
                q.order_by(AgentAction.created_at.desc())
                .offset(offset)
                .limit(limit)
                .all()
            )

            return {
                "actions": [
                    {
                        "id": a.id,
                        "action_type": a.action_type,
                        "target_entity": a.target_entity,
                        "target_id": a.target_id,
                        "description": a.description,
                        "payload": a.payload,
                        "created_at": a.created_at.isoformat() if a.created_at else None,
                    }
                    for a in actions
                ],
                "total": total,
                "limit": limit,
                "offset": offset,
            }

        except Exception as e:
            logger.exception(f"Failed to list pending actions: {e}")
            raise HTTPException(status_code=500, detail="Failed to list pending actions")

    # -------------------------------------------------------------------
    # POST /api/v1/autonomous/actions/{action_id}/approve
    # -------------------------------------------------------------------
    @app.post("/api/v1/autonomous/actions/{action_id}/approve", tags=["Autonomous Tasks"])
    async def approve_action(
        action_id: int,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """Approve a pending autonomous agent action and update confidence."""
        try:
            action = db.query(AgentAction).filter(AgentAction.id == action_id).first()
            if not action:
                raise HTTPException(status_code=404, detail="Action not found")
            if action.organization_id != current_user.organization_id:
                raise HTTPException(status_code=403, detail="Access denied")
            if action.status != "pending_approval":
                raise HTTPException(status_code=400, detail=f"Action status is '{action.status}', not pending_approval")

            # Replay the held action (execute the business operation)
            replayed = False
            try:
                from services.autonomous.action_dispatcher import ActionDispatcher
                dispatcher = ActionDispatcher(db, action.organization_id)
                replayed = dispatcher.replay(action)
            except Exception as e:
                logger.warning(f"Action replay failed for {action_id}: {e}")

            action.approved_by = current_user.id
            action.approved_at = datetime.now(timezone.utc)
            action.status = "completed" if replayed else "failed_replay"

            # Record decision in confidence graduation system
            confidence_result = None
            try:
                from services.autonomous.confidence_graduation import ConfidenceGraduationService
                grad_service = ConfidenceGraduationService(db)
                confidence_result = grad_service.record_decision(
                    org_id=current_user.organization_id,
                    action_type=action.action_type,
                    approved=True,
                )
            except Exception as e:
                logger.warning(f"Confidence update failed: {e}")

            db.commit()
            result = _action_to_dict(action)
            result["replayed"] = replayed
            if confidence_result:
                result["confidence"] = confidence_result
            return result

        except HTTPException:
            raise
        except Exception as e:
            db.rollback()
            logger.exception(f"Failed to approve action {action_id}: {e}")
            raise HTTPException(status_code=500, detail="Failed to approve action")

    # -------------------------------------------------------------------
    # POST /api/v1/autonomous/actions/{action_id}/reject
    # -------------------------------------------------------------------
    @app.post("/api/v1/autonomous/actions/{action_id}/reject", tags=["Autonomous Tasks"])
    async def reject_action(
        action_id: int,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """Reject a pending autonomous agent action and update confidence."""
        try:
            action = db.query(AgentAction).filter(AgentAction.id == action_id).first()
            if not action:
                raise HTTPException(status_code=404, detail="Action not found")
            if action.organization_id != current_user.organization_id:
                raise HTTPException(status_code=403, detail="Access denied")
            if action.status != "pending_approval":
                raise HTTPException(status_code=400, detail=f"Action status is '{action.status}', not pending_approval")

            # Reject the action
            action.status = "rejected"
            action.rejected_by = current_user.id
            action.rejected_at = datetime.now(timezone.utc)

            # Record rejection in confidence graduation system
            try:
                from services.autonomous.confidence_graduation import ConfidenceGraduationService
                grad_service = ConfidenceGraduationService(db)
                confidence_result = grad_service.record_decision(
                    org_id=current_user.organization_id,
                    action_type=action.action_type,
                    approved=False,
                )
            except Exception as e:
                logger.warning(f"Confidence update failed: {e}")
                confidence_result = None

            db.commit()
            result = _action_to_dict(action)
            if confidence_result:
                result["confidence"] = confidence_result
            return result

        except HTTPException:
            raise
        except Exception as e:
            db.rollback()
            logger.exception(f"Failed to reject action {action_id}: {e}")
            raise HTTPException(status_code=500, detail="Failed to reject action")

    # -------------------------------------------------------------------
    # GET /api/v1/autonomous/confidence — Graduation dashboard with trends
    # -------------------------------------------------------------------
    @app.get("/api/v1/autonomous/confidence", tags=["Autonomous Tasks"])
    async def confidence_dashboard(
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """Get confidence graduation status for all action types, including
        per-action-type decision trend data (last 7 days vs previous 7 days)."""
        try:
            from services.autonomous.confidence_graduation import ConfidenceGraduationService

            org_id = current_user.organization_id
            service = ConfidenceGraduationService(db)
            dashboard = service.get_confidence_dashboard(org_id)

            # Compute trend data: decisions in last 7 days vs previous 7 days
            now = datetime.now(timezone.utc)
            seven_days_ago = now - timedelta(days=7)
            fourteen_days_ago = now - timedelta(days=14)

            # Count recent-period decisions (approved or rejected actions)
            recent_rows = (
                db.query(
                    AgentAction.action_type,
                    func.count().label("cnt"),
                )
                .filter(
                    AgentAction.organization_id == org_id,
                    AgentAction.status.in_(["completed", "rejected"]),
                    AgentAction.approved_at >= seven_days_ago,
                )
                .group_by(AgentAction.action_type)
                .all()
            )
            recent_map = {row.action_type: row.cnt for row in recent_rows}

            # Count previous-period decisions
            previous_rows = (
                db.query(
                    AgentAction.action_type,
                    func.count().label("cnt"),
                )
                .filter(
                    AgentAction.organization_id == org_id,
                    AgentAction.status.in_(["completed", "rejected"]),
                    AgentAction.approved_at >= fourteen_days_ago,
                    AgentAction.approved_at < seven_days_ago,
                )
                .group_by(AgentAction.action_type)
                .all()
            )
            previous_map = {row.action_type: row.cnt for row in previous_rows}

            # Enrich each action_type entry with trend data
            for entry in dashboard.get("action_types", []):
                at = entry["action_type"]
                current_count = recent_map.get(at, 0)
                previous_count = previous_map.get(at, 0)
                if previous_count > 0:
                    trend_direction = "up" if current_count > previous_count else (
                        "down" if current_count < previous_count else "flat"
                    )
                elif current_count > 0:
                    trend_direction = "up"
                else:
                    trend_direction = "flat"
                entry["recent_decisions"] = {
                    "last_7_days": current_count,
                    "previous_7_days": previous_count,
                    "trend": trend_direction,
                }

            return dashboard

        except ImportError:
            raise HTTPException(status_code=501, detail="Confidence graduation not available")
        except Exception as e:
            logger.exception(f"Failed to get confidence dashboard: {e}")
            raise HTTPException(status_code=500, detail="Failed to get confidence dashboard")

    # -------------------------------------------------------------------
    # GET /api/v1/autonomous/circuits — Circuit breaker status
    # -------------------------------------------------------------------
    @app.get("/api/v1/autonomous/circuits", tags=["Autonomous Tasks"])
    async def get_circuit_breaker_status(
        current_user=Depends(get_current_user),
    ):
        """Get circuit breaker status for all org+agent pairs. Admin only."""
        _require_admin(current_user)
        try:
            from services.autonomous.circuit_breaker import get_circuit_breaker
            breaker = get_circuit_breaker()
            return {
                "circuits": breaker.get_status(),
                "open_circuits": breaker.get_open_circuits(),
            }
        except Exception as e:
            logger.exception(f"Failed to get circuit breaker status: {e}")
            raise HTTPException(status_code=500, detail="Failed to get circuit breaker status")

    # -------------------------------------------------------------------
    # POST /api/v1/autonomous/circuits/{org_id}/{agent_type}/reset
    # -------------------------------------------------------------------
    @app.post("/api/v1/autonomous/circuits/{org_id}/{agent_type}/reset", tags=["Autonomous Tasks"])
    async def reset_circuit_breaker(
        org_id: int,
        agent_type: str,
        current_user=Depends(get_current_user),
    ):
        """Manually reset a circuit breaker for a specific org+agent. Admin only."""
        _require_admin(current_user)
        try:
            from services.autonomous.circuit_breaker import get_circuit_breaker
            breaker = get_circuit_breaker()

            if agent_type not in KNOWN_AGENT_TYPES:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unknown agent_type '{agent_type}'. Must be one of: {sorted(KNOWN_AGENT_TYPES)}",
                )

            was_reset = breaker.reset(org_id, agent_type)
            if not was_reset:
                return {
                    "status": "no_circuit",
                    "message": f"No circuit found for org={org_id} agent={agent_type}",
                }

            logger.info(
                "Circuit breaker reset by user %s for org=%d agent=%s",
                current_user.id, org_id, agent_type,
            )
            return {
                "status": "reset",
                "org_id": org_id,
                "agent_type": agent_type,
                "message": f"Circuit for org={org_id} agent={agent_type} reset to CLOSED",
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.exception(f"Failed to reset circuit breaker: {e}")
            raise HTTPException(status_code=500, detail="Failed to reset circuit breaker")
