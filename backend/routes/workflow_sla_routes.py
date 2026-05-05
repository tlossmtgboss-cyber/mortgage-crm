"""
Workflow SLA System API Routes

API endpoints for the SLA-driven workflow task generation system.
Provides endpoints for:
- Workflow enrollment and management
- Task completion and tracking
- Role assignments
- Scheduled task execution
"""

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks, Request, Header
from sqlalchemy.orm import Session
from typing import Optional, List, Callable, Any
from pydantic import BaseModel
from datetime import datetime

from services.workflow_sla_service import WorkflowSLAService, get_workflow_service
from services.workflow_task_generator import TaskGeneratorService, get_task_generator
from services.workflow_role_assignment import RoleAssignmentService, get_role_assignment_service
from services.workflow_scheduler import WorkflowScheduler, run_scheduled_workflow_tasks

import logging
import os
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

_ADMIN_API_KEY = os.getenv("ADMIN_API_KEY")

router = APIRouter(prefix="/api/v1/workflow-sla", tags=["Workflow SLA"])

# ============================================================================
# DEPENDENCY INJECTION STORAGE
# ============================================================================

_get_db: Callable = None
_get_current_user: Callable = None
_User: Any = None


from db import get_db


def set_dependencies(get_db_func: Callable, get_current_user_func: Callable, user_model: Any):
    """Set dependencies from main.py to avoid circular imports."""
    global _get_db, _get_current_user, _User
    _get_db = get_db_func
    _get_current_user = get_current_user_func
    _User = user_model
    logger.info("Workflow SLA routes dependencies set")


async def get_current_user(request: Request, db: Session = Depends(get_db)):
    """Get current user dependency - wrapper for injected dependency."""
    if _get_current_user is None:
        raise RuntimeError("Workflow SLA routes not initialized. Call set_dependencies first.")
    # Extract token from authorization header
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else ""
    return await _get_current_user(token=token, request=request, db=db)


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================

class EnrollWorkflowRequest(BaseModel):
    workflow_key: str
    trigger_status: Optional[str] = None


class CompleteTaskRequest(BaseModel):
    completion_source: str = "user"  # user, ai, dialer, automation
    contact_made: bool = False
    notes: Optional[str] = None


class SkipTaskRequest(BaseModel):
    reason: str


class PauseWorkflowRequest(BaseModel):
    reason: Optional[str] = None


class CancelWorkflowRequest(BaseModel):
    reason: str


class AssignRoleRequest(BaseModel):
    role_id: int
    user_id: int


# =============================================================================
# WORKFLOW ENROLLMENT ENDPOINTS
# =============================================================================

@router.post("/leads/{lead_id}/enroll")
async def enroll_lead_in_workflow(
    lead_id: int,
    request: EnrollWorkflowRequest,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Enroll a lead in a workflow.

    Workflows available:
    - prospect: Initial lead engagement
    - prequal: Pre-qualification process
    - lead_purchase: Purchased lead follow-up
    - pre_approved: Pre-approval maintenance
    - credit_repair: Credit improvement tracking
    - nurture: Long-term relationship
    """
    service = get_workflow_service(db)
    result = service.enroll_lead(
        lead_id=lead_id,
        workflow_key=request.workflow_key,
        trigger_status=request.trigger_status,
        user_id=current_user.id
    )

    if not result["success"]:
        raise HTTPException(status_code=400, detail=result.get("error", "Enrollment failed"))

    return result


@router.post("/loans/{loan_id}/enroll")
async def enroll_loan_in_workflow(
    loan_id: int,
    request: EnrollWorkflowRequest,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Enroll a loan in a workflow.

    Workflows available:
    - under_contract: Active loan processing
    - last_mile: Final closing steps
    - post_close: Post-closing follow-up
    """
    service = get_workflow_service(db)
    result = service.enroll_loan(
        loan_id=loan_id,
        workflow_key=request.workflow_key,
        trigger_status=request.trigger_status,
        user_id=current_user.id
    )

    if not result["success"]:
        raise HTTPException(status_code=400, detail=result.get("error", "Enrollment failed"))

    return result


# =============================================================================
# WORKFLOW STATUS ENDPOINTS
# =============================================================================

@router.get("/instances/{instance_id}")
async def get_workflow_status(
    instance_id: int,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get detailed status of a workflow instance."""
    service = get_workflow_service(db)
    status = service.get_workflow_status(instance_id, organization_id=current_user.organization_id)

    if not status:
        raise HTTPException(status_code=404, detail="Workflow instance not found")

    return status


@router.get("/leads/{lead_id}/workflows")
async def get_lead_workflows(
    lead_id: int,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all active workflows for a lead."""
    service = get_workflow_service(db)
    return {"workflows": service.get_active_workflows_for_lead(lead_id, organization_id=current_user.organization_id)}


@router.get("/loans/{loan_id}/workflows")
async def get_loan_workflows(
    loan_id: int,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all active workflows for a loan."""
    service = get_workflow_service(db)
    return {"workflows": service.get_active_workflows_for_loan(loan_id, organization_id=current_user.organization_id)}


# =============================================================================
# WORKFLOW CONTROL ENDPOINTS
# =============================================================================

@router.post("/instances/{instance_id}/pause")
async def pause_workflow(
    instance_id: int,
    request: PauseWorkflowRequest,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Pause an active workflow."""
    service = get_workflow_service(db)
    result = service.pause_workflow(
        instance_id=instance_id,
        reason=request.reason,
        user_id=current_user.id
    )

    if not result["success"]:
        raise HTTPException(status_code=400, detail=result.get("error", "Pause failed"))

    return result


@router.post("/instances/{instance_id}/resume")
async def resume_workflow(
    instance_id: int,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Resume a paused workflow."""
    service = get_workflow_service(db)
    result = service.resume_workflow(
        instance_id=instance_id,
        user_id=current_user.id
    )

    if not result["success"]:
        raise HTTPException(status_code=400, detail=result.get("error", "Resume failed"))

    return result


@router.post("/instances/{instance_id}/cancel")
async def cancel_workflow(
    instance_id: int,
    request: CancelWorkflowRequest,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Cancel a workflow instance."""
    service = get_workflow_service(db)
    result = service.cancel_workflow(
        instance_id=instance_id,
        reason=request.reason,
        user_id=current_user.id
    )

    if not result["success"]:
        raise HTTPException(status_code=400, detail=result.get("error", "Cancel failed"))

    return result


# =============================================================================
# TASK MANAGEMENT ENDPOINTS
# =============================================================================

@router.post("/tasks/{task_instance_id}/complete")
async def complete_workflow_task(
    task_instance_id: int,
    request: CompleteTaskRequest,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Complete a workflow task.

    If contact_made is True, sibling tasks in the same group will be cancelled.
    """
    service = get_workflow_service(db)
    result = service.complete_task(
        task_instance_id=task_instance_id,
        completion_source=request.completion_source,
        completed_by_id=current_user.id,
        outcome={
            "contact_made": request.contact_made,
            "notes": request.notes
        }
    )

    if not result["success"]:
        raise HTTPException(status_code=400, detail=result.get("error", "Completion failed"))

    return result


@router.post("/tasks/{task_instance_id}/skip")
async def skip_workflow_task(
    task_instance_id: int,
    request: SkipTaskRequest,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Skip a workflow task with a reason."""
    service = get_workflow_service(db)
    result = service.skip_task(
        task_instance_id=task_instance_id,
        reason=request.reason,
        user_id=current_user.id
    )

    if not result["success"]:
        raise HTTPException(status_code=400, detail=result.get("error", "Skip failed"))

    return result


@router.post("/instances/{instance_id}/generate-tasks")
async def generate_workflow_tasks(
    instance_id: int,
    force: bool = Query(False, description="Force regeneration of already generated days"),
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Generate tasks for a workflow instance.

    Normally tasks are generated automatically by the scheduler.
    This endpoint allows manual generation.
    """
    generator = get_task_generator(db)
    result = generator.generate_tasks_for_instance(
        instance_id=instance_id,
        force_regenerate=force
    )

    if not result["success"]:
        raise HTTPException(status_code=400, detail=result.get("error", "Generation failed"))

    return result


# =============================================================================
# ROLE ASSIGNMENT ENDPOINTS
# =============================================================================

@router.get("/leads/{lead_id}/roles")
async def get_lead_role_assignments(
    lead_id: int,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all role assignments for a lead."""
    service = get_role_assignment_service(db)
    return {"assignments": service.get_lead_role_assignments(lead_id)}


@router.post("/leads/{lead_id}/roles")
async def assign_lead_role(
    lead_id: int,
    request: AssignRoleRequest,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Assign a user to a role for a lead."""
    service = get_role_assignment_service(db)
    result = service.assign_role_to_lead(
        lead_id=lead_id,
        role_id=request.role_id,
        user_id=request.user_id,
        assigned_by_id=current_user.id
    )

    if not result["success"]:
        raise HTTPException(status_code=400, detail=result.get("error", "Assignment failed"))

    return result


@router.delete("/leads/{lead_id}/roles/{role_id}")
async def remove_lead_role(
    lead_id: int,
    role_id: int,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Remove a role assignment from a lead."""
    service = get_role_assignment_service(db)
    result = service.remove_role_from_lead(lead_id=lead_id, role_id=role_id)

    if not result["success"]:
        raise HTTPException(status_code=400, detail=result.get("error", "Removal failed"))

    return result


@router.get("/loans/{loan_id}/roles")
async def get_loan_role_assignments(
    loan_id: int,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all role assignments for a loan."""
    service = get_role_assignment_service(db)
    return {"assignments": service.get_loan_role_assignments(loan_id)}


@router.post("/loans/{loan_id}/roles")
async def assign_loan_role(
    loan_id: int,
    request: AssignRoleRequest,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Assign a user to a role for a loan."""
    service = get_role_assignment_service(db)
    result = service.assign_role_to_loan(
        loan_id=loan_id,
        role_id=request.role_id,
        user_id=request.user_id,
        assigned_by_id=current_user.id
    )

    if not result["success"]:
        raise HTTPException(status_code=400, detail=result.get("error", "Assignment failed"))

    return result


@router.delete("/loans/{loan_id}/roles/{role_id}")
async def remove_loan_role(
    loan_id: int,
    role_id: int,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Remove a role assignment from a loan."""
    service = get_role_assignment_service(db)
    result = service.remove_role_from_loan(loan_id=loan_id, role_id=role_id)

    if not result["success"]:
        raise HTTPException(status_code=400, detail=result.get("error", "Removal failed"))

    return result


@router.post("/loans/{loan_id}/roles/copy-from-lead/{lead_id}")
async def copy_roles_from_lead(
    loan_id: int,
    lead_id: int,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Copy role assignments from a lead to a loan."""
    service = get_role_assignment_service(db)
    result = service.copy_assignments_lead_to_loan(lead_id=lead_id, loan_id=loan_id)

    if not result["success"]:
        raise HTTPException(status_code=400, detail=result.get("error", "Copy failed"))

    return result


@router.get("/roles/available")
async def get_available_roles(
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all available roles for assignment."""
    service = get_role_assignment_service(db)
    return {"roles": service.get_available_roles()}


# =============================================================================
# SCHEDULER ENDPOINTS
# =============================================================================

def run_scheduled_workflow_tasks_background():
    """Wrapper that creates its own db session for background execution"""
    from database import SessionLocal
    db = SessionLocal()
    try:
        result = run_scheduled_workflow_tasks(db)
        db.commit()
        return result
    except Exception as e:
        db.rollback()
        logger.error(f"Background scheduler error: {e}")
        raise
    finally:
        db.close()


@router.post("/scheduler/run")
async def run_scheduler(
    background_tasks: BackgroundTasks,
    run_async: bool = Query(False, description="Run in background"),
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Run the workflow scheduler.

    Processes status changes, generates tasks, escalates overdue items,
    and checks for workflow completions.
    """
    if run_async:
        background_tasks.add_task(run_scheduled_workflow_tasks_background)
        return {"success": True, "message": "Scheduler started in background"}

    result = run_scheduled_workflow_tasks(db)
    return result


@router.post("/scheduler/generate-tasks")
async def run_task_generation(
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Run task generation for all active workflows."""
    scheduler = WorkflowScheduler(db)
    result = scheduler.generate_due_tasks()
    return result


@router.post("/scheduler/process-status-changes")
async def run_status_processing(
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Process status changes and enroll entities in appropriate workflows."""
    scheduler = WorkflowScheduler(db)
    result = scheduler.process_status_changes()
    return result


@router.post("/scheduler/escalate-overdue")
async def run_escalation(
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Escalate overdue workflow tasks."""
    scheduler = WorkflowScheduler(db)
    result = scheduler.escalate_overdue_tasks()
    return result


@router.post("/scheduler/check-completions")
async def run_completion_check(
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Check for workflows that should be completed or cancelled."""
    scheduler = WorkflowScheduler(db)
    result = scheduler.check_workflow_completions()
    return result


# =============================================================================
# AI EVALUATION ENDPOINTS
# =============================================================================

class EvaluateTaskRequest(BaseModel):
    auto_execute: bool = False


class EvaluateBatchRequest(BaseModel):
    task_instance_ids: List[int]
    auto_execute: bool = False


class ExecuteTaskRequest(BaseModel):
    force_execute: bool = False
    user_override: bool = False
    context: Optional[dict] = None


@router.post("/ai/evaluate/{task_instance_id}")
async def evaluate_task_confidence(
    task_instance_id: int,
    request: EvaluateTaskRequest,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Evaluate AI confidence for a workflow task.

    Returns confidence score and recommendation for the task.
    """
    from services.workflow_ai_evaluator import WorkflowAIEvaluator

    evaluator = WorkflowAIEvaluator(db)
    result = evaluator.evaluate_task(
        task_instance_id=task_instance_id,
        auto_execute=request.auto_execute
    )

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Evaluation failed"))

    return result


@router.post("/ai/evaluate-batch")
async def evaluate_batch_confidence(
    request: EvaluateBatchRequest,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Evaluate AI confidence for multiple tasks."""
    from services.workflow_ai_evaluator import WorkflowAIEvaluator

    evaluator = WorkflowAIEvaluator(db)
    result = evaluator.evaluate_batch(
        task_instance_ids=request.task_instance_ids,
        auto_execute=request.auto_execute
    )

    return result


@router.get("/ai/pending-tasks")
async def get_pending_ai_tasks(
    limit: int = Query(100, le=500),
    task_types: Optional[str] = Query(None, description="Comma-separated task types"),
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get tasks pending AI evaluation."""
    from services.workflow_ai_evaluator import WorkflowAIEvaluator

    evaluator = WorkflowAIEvaluator(db)
    types_list = task_types.split(",") if task_types else None
    tasks = evaluator.get_pending_ai_tasks(limit=limit, task_types=types_list)

    return {"tasks": tasks, "count": len(tasks)}


@router.post("/ai/execute/{task_instance_id}")
async def execute_ai_task(
    task_instance_id: int,
    request: ExecuteTaskRequest,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Execute a workflow task via AI.

    Requires sufficient confidence unless force_execute or user_override is set.
    """
    from services.workflow_ai_executor import WorkflowAIExecutor

    executor = WorkflowAIExecutor(db)
    result = executor.execute_task(
        task_instance_id=task_instance_id,
        force_execute=request.force_execute,
        user_override=request.user_override,
        context=request.context
    )

    if not result.get("success") and not result.get("requires_approval"):
        raise HTTPException(status_code=400, detail=result.get("error", "Execution failed"))

    return result


@router.get("/ai/ready-for-execution")
async def get_ready_for_ai_execution(
    limit: int = Query(50, le=200),
    task_types: Optional[str] = Query(None, description="Comma-separated task types"),
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get tasks ready for AI execution with confidence scores."""
    from services.workflow_ai_executor import WorkflowAIExecutor

    executor = WorkflowAIExecutor(db)
    types_list = task_types.split(",") if task_types else None
    tasks = executor.get_ready_for_execution(
        user_id=current_user.id,
        task_types=types_list,
        limit=limit
    )

    return {
        "tasks": tasks,
        "count": len(tasks),
        "auto_executable_count": len([t for t in tasks if t.get("auto_executable")])
    }


@router.post("/ai/run-autonomous")
async def run_autonomous_execution(
    background_tasks: BackgroundTasks,
    max_tasks: int = Query(20, le=100),
    run_async: bool = Query(False, description="Run in background"),
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Run autonomous AI task execution.

    Processes high-confidence tasks without human intervention.
    """
    from services.workflow_ai_executor import run_autonomous_ai_tasks

    if run_async:
        background_tasks.add_task(run_autonomous_ai_tasks, db, max_tasks)
        return {"success": True, "message": "Autonomous execution started in background"}

    result = run_autonomous_ai_tasks(db, max_tasks)
    return result


# =============================================================================
# DIALER INTEGRATION ENDPOINTS
# =============================================================================

class CreateDialerSessionRequest(BaseModel):
    workflow_task_ids: List[int]


class AddToSessionRequest(BaseModel):
    workflow_task_ids: List[int]


class DialerCompletionRequest(BaseModel):
    call_status: str
    call_duration: Optional[int] = None
    disposition: Optional[str] = None
    notes: Optional[str] = None


@router.get("/dialer/phone-tasks")
async def get_phone_tasks_for_dialer(
    lead_ids: Optional[str] = Query(None, description="Comma-separated lead IDs"),
    loan_ids: Optional[str] = Query(None, description="Comma-separated loan IDs"),
    limit: int = Query(50, le=200),
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get workflow phone tasks that can be added to a dialer session."""
    from services.workflow_dialer_integration import WorkflowDialerIntegration

    integration = WorkflowDialerIntegration(db)
    lead_list = [int(x) for x in lead_ids.split(",")] if lead_ids else None
    loan_list = [int(x) for x in loan_ids.split(",")] if loan_ids else None

    tasks = integration.get_phone_tasks_for_dialer(
        user_id=current_user.id,
        lead_ids=lead_list,
        loan_ids=loan_list,
        limit=limit
    )

    return {"tasks": tasks, "count": len(tasks)}


@router.post("/dialer/create-session")
async def create_dialer_session_from_workflow(
    request: CreateDialerSessionRequest,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create a dialer session from workflow tasks.

    Links workflow phone tasks to a new dialer session for power dialing.
    """
    from services.workflow_dialer_integration import WorkflowDialerIntegration

    dialer_base_url = os.getenv("DIALER_BASE_URL", "")
    if not dialer_base_url:
        raise HTTPException(status_code=503, detail="Dialer service not configured")

    integration = WorkflowDialerIntegration(db)

    result = integration.create_dialer_session_from_workflow(
        agent_id=current_user.id,
        workflow_task_ids=request.workflow_task_ids,
        base_url=dialer_base_url
    )

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Session creation failed"))

    return result


@router.post("/dialer/sessions/{session_id}/add-tasks")
async def add_workflow_tasks_to_session(
    session_id: int,
    request: AddToSessionRequest,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Add workflow tasks to an existing dialer session."""
    from services.workflow_dialer_integration import WorkflowDialerIntegration

    integration = WorkflowDialerIntegration(db)
    result = integration.add_workflow_tasks_to_session(
        session_id=session_id,
        workflow_task_ids=request.workflow_task_ids
    )

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to add tasks"))

    return result


@router.post("/dialer/task-completion/{dialer_session_task_id}")
async def handle_dialer_task_completion(
    dialer_session_task_id: int,
    request: DialerCompletionRequest,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Handle dialer completion callback for a workflow task.

    Updates workflow task status and handles sibling task cancellation
    when contact is made.
    """
    from services.workflow_dialer_integration import WorkflowDialerIntegration

    integration = WorkflowDialerIntegration(db)
    result = integration.handle_dialer_task_completion(
        dialer_session_task_id=dialer_session_task_id,
        call_status=request.call_status,
        call_duration=request.call_duration,
        disposition=request.disposition,
        notes=request.notes
    )

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Completion handling failed"))

    return result


@router.get("/dialer/queue")
async def get_dialer_queue(
    include_due_only: bool = Query(True, description="Only include tasks that are due"),
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get the dialer queue summary for the current user."""
    from services.workflow_dialer_integration import WorkflowDialerIntegration

    integration = WorkflowDialerIntegration(db)
    result = integration.get_dialer_queue_for_user(
        user_id=current_user.id,
        include_due_only=include_due_only
    )

    return result


# =============================================================================
# INITIALIZATION / SETUP ENDPOINTS
# =============================================================================

@router.post("/init/ensure-tasks-columns")
async def ensure_tasks_table_columns(
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Ensure all required columns exist on the tasks table.
    This is a safe operation that only adds missing columns.
    Requires platform_admin or admin role.
    """
    user_role = getattr(current_user, 'role', None) or getattr(current_user, 'permission_role', None)
    if user_role not in ('platform_admin', 'admin', 'site_admin'):
        raise HTTPException(status_code=403, detail="Admin access required")
    from sqlalchemy import text

    # List of columns to ensure exist
    columns_to_add = [
        ("sla_milestone_id", "INTEGER"),
        ("sla_milestone_type", "VARCHAR(100)"),
        ("sla_date_field", "VARCHAR(100)"),
        ("milestone_date", "TIMESTAMP WITH TIME ZONE"),
        ("workflow_task_instance_id", "INTEGER"),
        ("task_group_key", "VARCHAR(100)"),
    ]

    added = []
    already_exists = []
    errors = []

    for col_name, col_type in columns_to_add:
        try:
            check_sql = "SELECT column_name FROM information_schema.columns WHERE table_name = 'tasks' AND column_name = :col_name"
            result = db.execute(text(check_sql), {"col_name": col_name})
            if not result.fetchone():
                alter_sql = "ALTER TABLE tasks ADD COLUMN " + col_name + " " + col_type
                db.execute(text(alter_sql))
                db.commit()
                added.append(col_name)
                logger.info(f"✅ Added '{col_name}' column to tasks table")
            else:
                already_exists.append(col_name)
        except SQLAlchemyError as e:
            db.rollback()
            errors.append({"column": col_name, "error": "Internal server error"})
            logger.warning(f"⚠️ Error with '{col_name}': {e}")

    return {
        "success": len(errors) == 0,
        "added": added,
        "already_exists": already_exists,
        "errors": errors
    }


@router.post("/init/run-migrations")
async def run_workflow_migrations(
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Run the full workflow SLA migrations.
    Creates all required tables and enum types for the workflow system.
    """
    from sqlalchemy import text
    import os

    results = {
        "enums": [],
        "tables": [],
        "indexes": [],
        "errors": []
    }

    # Define all migrations inline for reliability
    migrations = [
        # Enum types
        ("""DO $$ BEGIN
            CREATE TYPE workflow_instance_status AS ENUM (
                'active', 'paused', 'completed', 'cancelled', 'error'
            );
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;""", "enum", "workflow_instance_status"),

        ("""DO $$ BEGIN
            CREATE TYPE workflow_task_status AS ENUM (
                'scheduled', 'pending', 'in_progress', 'completed', 'skipped', 'failed', 'cancelled'
            );
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;""", "enum", "workflow_task_status"),

        ("""DO $$ BEGIN
            CREATE TYPE workflow_task_type AS ENUM (
                'phone', 'phone_am', 'phone_pm', 'text', 'text_am', 'text_pm',
                'email', 'referral_partner', 'dialer', 'manual'
            );
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;""", "enum", "workflow_task_type"),

        ("""DO $$ BEGIN
            CREATE TYPE workflow_route AS ENUM (
                'task_list', 'dialer_queue', 'ai_autonomous', 'email_automation', 'sms_automation'
            );
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;""", "enum", "workflow_route"),

        ("""DO $$ BEGIN
            CREATE TYPE lead_source_category AS ENUM (
                'organic', 'purchased', 'partner', 'marketing', 'other'
            );
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;""", "enum", "lead_source_category"),

        # Tables
        ("""CREATE TABLE IF NOT EXISTS workflow_instances (
            id SERIAL PRIMARY KEY,
            organization_id INTEGER NOT NULL,
            lead_id INTEGER,
            loan_id INTEGER,
            workflow_type VARCHAR(100) NOT NULL,
            workflow_config_id INTEGER,
            status VARCHAR(50) DEFAULT 'active',
            current_day INTEGER DEFAULT 1,
            started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            paused_at TIMESTAMP WITH TIME ZONE,
            completed_at TIMESTAMP WITH TIME ZONE,
            cancelled_at TIMESTAMP WITH TIME ZONE,
            next_check_at TIMESTAMP WITH TIME ZONE,
            metadata JSONB DEFAULT '{}',
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );""", "table", "workflow_instances"),

        ("""CREATE TABLE IF NOT EXISTS workflow_task_instances (
            id SERIAL PRIMARY KEY,
            workflow_instance_id INTEGER NOT NULL,
            task_type VARCHAR(50) NOT NULL,
            task_name VARCHAR(255) NOT NULL,
            day_number INTEGER NOT NULL,
            status VARCHAR(50) DEFAULT 'scheduled',
            route VARCHAR(50) DEFAULT 'task_list',
            assigned_user_id INTEGER,
            lead_id INTEGER,
            loan_id INTEGER,
            due_date TIMESTAMP WITH TIME ZONE,
            started_at TIMESTAMP WITH TIME ZONE,
            completed_at TIMESTAMP WITH TIME ZONE,
            outcome VARCHAR(100),
            outcome_notes TEXT,
            ai_confidence DECIMAL(5,4),
            ai_executed BOOLEAN DEFAULT FALSE,
            execution_details JSONB DEFAULT '{}',
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );""", "table", "workflow_task_instances"),

        ("""CREATE TABLE IF NOT EXISTS workflow_role_assignments (
            id SERIAL PRIMARY KEY,
            organization_id INTEGER NOT NULL,
            lead_id INTEGER,
            loan_id INTEGER,
            workflow_type VARCHAR(100) NOT NULL,
            role_type VARCHAR(50) NOT NULL,
            user_id INTEGER NOT NULL,
            assigned_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            assigned_by INTEGER,
            active BOOLEAN DEFAULT TRUE,
            notes TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );""", "table", "workflow_role_assignments"),

        ("""CREATE TABLE IF NOT EXISTS workflow_ai_actions (
            id SERIAL PRIMARY KEY,
            workflow_task_instance_id INTEGER NOT NULL,
            action_type VARCHAR(100) NOT NULL,
            confidence_score DECIMAL(5,4) NOT NULL,
            confidence_threshold DECIMAL(5,4) NOT NULL,
            was_executed BOOLEAN DEFAULT FALSE,
            required_approval BOOLEAN DEFAULT FALSE,
            approval_status VARCHAR(50),
            approved_by INTEGER,
            approved_at TIMESTAMP WITH TIME ZONE,
            execution_result JSONB,
            error_message TEXT,
            rollback_available BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );""", "table", "workflow_ai_actions"),

        ("""CREATE TABLE IF NOT EXISTS workflow_transitions (
            id SERIAL PRIMARY KEY,
            workflow_instance_id INTEGER NOT NULL,
            from_status VARCHAR(50),
            to_status VARCHAR(50) NOT NULL,
            trigger_type VARCHAR(100) NOT NULL,
            trigger_details JSONB,
            transitioned_by INTEGER,
            notes TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );""", "table", "workflow_transitions"),

        # Indexes
        ("""CREATE INDEX IF NOT EXISTS idx_workflow_instances_org_status
            ON workflow_instances(organization_id, status);""", "index", "idx_workflow_instances_org_status"),
        ("""CREATE INDEX IF NOT EXISTS idx_workflow_instances_lead
            ON workflow_instances(lead_id) WHERE lead_id IS NOT NULL;""", "index", "idx_workflow_instances_lead"),
        ("""CREATE INDEX IF NOT EXISTS idx_workflow_instances_loan
            ON workflow_instances(loan_id) WHERE loan_id IS NOT NULL;""", "index", "idx_workflow_instances_loan"),
        ("""CREATE INDEX IF NOT EXISTS idx_workflow_task_instances_workflow
            ON workflow_task_instances(workflow_instance_id, status);""", "index", "idx_workflow_task_instances_workflow"),
        ("""CREATE INDEX IF NOT EXISTS idx_workflow_task_instances_assigned
            ON workflow_task_instances(assigned_user_id, status, due_date);""", "index", "idx_workflow_task_instances_assigned"),
    ]

    for sql, migration_type, name in migrations:
        try:
            db.execute(text(sql))
            db.commit()
            results[f"{migration_type}s"].append({"name": name, "status": "success"})
            logger.info(f"✅ Created {migration_type}: {name}")
        except SQLAlchemyError as e:
            db.rollback()
            error_msg = str(e)
            if "already exists" in error_msg.lower():
                results[f"{migration_type}s"].append({"name": name, "status": "exists"})
            else:
                results["errors"].append({"name": name, "type": migration_type, "error": error_msg})
                logger.error(f"❌ Failed {migration_type} {name}: {e}")

    return {
        "success": len(results["errors"]) == 0,
        "results": results,
        "summary": {
            "enums": len([e for e in results["enums"] if e["status"] == "success"]),
            "tables": len([t for t in results["tables"] if t["status"] == "success"]),
            "indexes": len([i for i in results["indexes"] if i["status"] == "success"]),
            "errors": len(results["errors"])
        }
    }


@router.post("/init/repair-tables")
async def repair_workflow_tables(
    admin_key: str = None,
    db: Session = Depends(get_db)
):
    """
    Repair workflow tables by adding any missing columns.
    Safe to run multiple times - skips existing columns.
    Requires admin_key query parameter for access.
    """
    if admin_key != _ADMIN_API_KEY or not _ADMIN_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized - admin_key required")
    from sqlalchemy import text

    results = {
        "leads": [],
        "loans": [],
        "workflow_configurations": [],
        "workflow_instances": [],
        "workflow_task_instances": [],
        "workflow_role_assignments": [],
        "errors": []
    }

    # Define expected columns for each table
    table_columns = {
        "leads": [
            ("current_workflow_instance_id", "INTEGER"),  # Links to active workflow instance
        ],
        "loans": [
            ("current_workflow_instance_id", "INTEGER"),  # Links to active workflow instance
        ],
        "workflow_configurations": [
            ("organization_id", "INTEGER"),  # For multi-tenancy
            ("is_system_template", "BOOLEAN DEFAULT FALSE"),  # True for system-wide templates
            ("is_active", "BOOLEAN DEFAULT TRUE"),
            ("entity_type", "VARCHAR(50) DEFAULT 'loan'"),  # 'lead' or 'loan'
            ("trigger_type", "VARCHAR(50)"),  # 'status_change', 'salesforce_date', etc.
            ("trigger_field", "VARCHAR(100)"),  # Field that triggers workflow (e.g. 'closing_date')
        ],
        "workflow_instances": [
            ("organization_id", "INTEGER NOT NULL DEFAULT 1"),
            ("lead_id", "INTEGER"),
            ("loan_id", "INTEGER"),
            ("workflow_type", "VARCHAR(100) NOT NULL DEFAULT 'prospect'"),
            ("workflow_config_id", "INTEGER"),
            ("workflow_configuration_id", "INTEGER"),  # Alias for workflow_config_id
            ("status", "VARCHAR(50) DEFAULT 'active'"),
            ("current_day", "INTEGER DEFAULT 1"),
            ("started_at", "TIMESTAMP WITH TIME ZONE DEFAULT NOW()"),
            ("paused_at", "TIMESTAMP WITH TIME ZONE"),
            ("completed_at", "TIMESTAMP WITH TIME ZONE"),
            ("cancelled_at", "TIMESTAMP WITH TIME ZONE"),
            ("cancelled_by_id", "INTEGER"),  # User who cancelled
            ("cancellation_reason", "TEXT"),  # Reason for cancellation
            ("superseded_by_id", "INTEGER"),  # Reference to new workflow instance
            ("trigger_milestone_status", "VARCHAR(100)"),  # Status that triggered enrollment
            ("trigger_milestone_entered_at", "TIMESTAMP WITH TIME ZONE"),  # When trigger status was entered
            ("next_check_at", "TIMESTAMP WITH TIME ZONE"),
            ("next_task_due_at", "TIMESTAMP WITH TIME ZONE"),  # For task scheduling
            ("last_task_generated_day", "INTEGER DEFAULT 0"),  # Track task generation progress
            ("metadata", "JSONB DEFAULT '{}'"),
            ("created_at", "TIMESTAMP WITH TIME ZONE DEFAULT NOW()"),
            ("updated_at", "TIMESTAMP WITH TIME ZONE DEFAULT NOW()"),
        ],
        "workflow_task_instances": [
            ("workflow_instance_id", "INTEGER"),
            ("workflow_id", "INTEGER"),  # Reference to workflow configuration
            ("day_config_id", "INTEGER"),  # Reference to day configuration
            ("organization_id", "INTEGER"),  # Organization for the task
            ("task_type", "VARCHAR(50) NOT NULL DEFAULT 'manual'"),
            ("task_name", "VARCHAR(255) NOT NULL DEFAULT 'Task'"),
            ("task_description", "TEXT"),  # Task description from day config
            ("day_number", "INTEGER NOT NULL DEFAULT 1"),
            ("status", "VARCHAR(50) DEFAULT 'scheduled'"),
            ("route", "VARCHAR(50) DEFAULT 'task_list'"),
            ("task_group_key", "VARCHAR(100)"),  # For sibling task cancellation
            ("assigned_user_id", "INTEGER"),
            ("assigned_role_id", "INTEGER"),  # Role responsible for task
            ("lead_id", "INTEGER"),
            ("loan_id", "INTEGER"),
            ("scheduled_date", "TIMESTAMP WITH TIME ZONE"),  # Scheduled date
            ("due_date", "TIMESTAMP WITH TIME ZONE"),
            ("ai_eligible", "BOOLEAN DEFAULT FALSE"),  # Can AI execute this task
            ("linked_task_id", "INTEGER"),  # Link to main tasks table
            ("completion_source", "VARCHAR(50)"),  # user, ai, dialer, automation
            ("completed_by_id", "INTEGER"),  # User who completed
            ("health_status", "VARCHAR(50) DEFAULT 'healthy'"),  # For escalation tracking
            ("error_message", "TEXT"),  # For error details
            ("started_at", "TIMESTAMP WITH TIME ZONE"),
            ("completed_at", "TIMESTAMP WITH TIME ZONE"),
            ("outcome", "VARCHAR(100)"),
            ("outcome_notes", "TEXT"),
            ("ai_confidence", "DECIMAL(5,4)"),
            ("ai_executed", "BOOLEAN DEFAULT FALSE"),
            ("execution_details", "JSONB DEFAULT '{}'"),
            ("created_at", "TIMESTAMP WITH TIME ZONE DEFAULT NOW()"),
            ("updated_at", "TIMESTAMP WITH TIME ZONE DEFAULT NOW()"),
        ],
        "workflow_role_assignments": [
            ("organization_id", "INTEGER NOT NULL DEFAULT 1"),
            ("lead_id", "INTEGER"),
            ("loan_id", "INTEGER"),
            ("workflow_type", "VARCHAR(100) NOT NULL DEFAULT 'prospect'"),
            ("role_type", "VARCHAR(50) NOT NULL DEFAULT 'lo'"),
            ("user_id", "INTEGER NOT NULL DEFAULT 1"),
            ("assigned_at", "TIMESTAMP WITH TIME ZONE DEFAULT NOW()"),
            ("assigned_by", "INTEGER"),
            ("active", "BOOLEAN DEFAULT TRUE"),
            ("notes", "TEXT"),
            ("created_at", "TIMESTAMP WITH TIME ZONE DEFAULT NOW()"),
            ("updated_at", "TIMESTAMP WITH TIME ZONE DEFAULT NOW()"),
        ],
    }

    for table_name, columns in table_columns.items():
        for col_name, col_def in columns:
            try:
                # Check if column exists
                check_sql = "SELECT column_name FROM information_schema.columns WHERE table_name = :table_name AND column_name = :col_name"
                result = db.execute(text(check_sql), {"table_name": table_name, "col_name": col_name})
                if not result.fetchone():
                    # Add the column
                    alter_sql = "ALTER TABLE " + table_name + " ADD COLUMN " + col_name + " " + col_def
                    db.execute(text(alter_sql))
                    db.commit()
                    results[table_name].append({"column": col_name, "status": "added"})
                    logger.info(f"✅ Added column {col_name} to {table_name}")
                else:
                    results[table_name].append({"column": col_name, "status": "exists"})
            except SQLAlchemyError as e:
                db.rollback()
                results["errors"].append({"table": table_name, "column": col_name, "error": "Internal server error"})
                logger.error(f"❌ Error adding {col_name} to {table_name}: {e}")

    # Create indexes
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_wf_instances_org_status ON workflow_instances(organization_id, status)",
        "CREATE INDEX IF NOT EXISTS idx_wf_instances_lead ON workflow_instances(lead_id) WHERE lead_id IS NOT NULL",
        "CREATE INDEX IF NOT EXISTS idx_wf_instances_loan ON workflow_instances(loan_id) WHERE loan_id IS NOT NULL",
        "CREATE INDEX IF NOT EXISTS idx_wf_task_workflow ON workflow_task_instances(workflow_instance_id, status)",
        "CREATE INDEX IF NOT EXISTS idx_wf_task_assigned ON workflow_task_instances(assigned_user_id, status, due_date)",
    ]

    for idx_sql in indexes:
        try:
            db.execute(text(idx_sql))
            db.commit()
        except SQLAlchemyError as e:
            db.rollback()
            # Ignore index errors - not critical

    # Create role assignment tables if they don't exist
    role_tables_created = []
    role_table_sql = """
    -- Lead-level role assignments
    CREATE TABLE IF NOT EXISTS lead_workflow_role_assignments (
        id SERIAL PRIMARY KEY,
        organization_id INTEGER NOT NULL DEFAULT 1,
        lead_id INTEGER NOT NULL,
        role_id INTEGER NOT NULL,
        assigned_user_id INTEGER NOT NULL,
        assigned_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
        assigned_by_id INTEGER,
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        deactivated_at TIMESTAMP WITH TIME ZONE,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    -- Loan-level role assignments
    CREATE TABLE IF NOT EXISTS loan_workflow_role_assignments (
        id SERIAL PRIMARY KEY,
        organization_id INTEGER NOT NULL DEFAULT 1,
        loan_id INTEGER NOT NULL,
        role_id INTEGER NOT NULL,
        assigned_user_id INTEGER NOT NULL,
        assigned_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
        assigned_by_id INTEGER,
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        deactivated_at TIMESTAMP WITH TIME ZONE,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    -- Create indexes for performance
    CREATE INDEX IF NOT EXISTS ix_lead_role_assignments_lead
        ON lead_workflow_role_assignments(lead_id, is_active);

    CREATE INDEX IF NOT EXISTS ix_lead_role_assignments_user
        ON lead_workflow_role_assignments(assigned_user_id, is_active);

    CREATE INDEX IF NOT EXISTS ix_loan_role_assignments_loan
        ON loan_workflow_role_assignments(loan_id, is_active);

    CREATE INDEX IF NOT EXISTS ix_loan_role_assignments_user
        ON loan_workflow_role_assignments(assigned_user_id, is_active);
    """

    try:
        db.execute(text(role_table_sql))
        db.commit()
        # Check which tables were created
        for table_name in ['lead_workflow_role_assignments', 'loan_workflow_role_assignments']:
            check_sql = "SELECT 1 FROM information_schema.tables WHERE table_name = :table_name AND table_schema = 'public'"
            result = db.execute(text(check_sql), {"table_name": table_name})
            if result.fetchone():
                role_tables_created.append(table_name)
        logger.info(f"Role assignment tables created: {role_tables_created}")
    except SQLAlchemyError as e:
        db.rollback()
        results["errors"].append({"section": "role_tables", "error": "Internal server error"})
        logger.error(f"Error creating role assignment tables: {e}")

    results["role_tables"] = role_tables_created

    added_count = sum(len([c for c in cols if c.get("status") == "added"]) for cols in results.values() if isinstance(cols, list))

    return {
        "success": len(results["errors"]) == 0,
        "results": results,
        "summary": {
            "columns_added": added_count,
            "errors": len(results["errors"])
        }
    }


@router.get("/init/debug-imports")
async def debug_imports(
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Debug endpoint to test imports and model initialization.
    """
    results = {
        "main_imports": {},
        "workflow_config_imports": {},
        "service_init": {},
        "errors": []
    }

    # Test main imports
    try:
        from database import Base
        from database.models import Lead, Loan, Task, User, Organization
        results["main_imports"]["Lead"] = str(type(Lead))
        results["main_imports"]["Loan"] = str(type(Loan))
        results["main_imports"]["Task"] = str(type(Task))
        results["main_imports"]["User"] = str(type(User))
        results["main_imports"]["Organization"] = str(type(Organization))
        results["main_imports"]["Base"] = str(type(Base))
    except Exception as e:
        results["errors"].append({"stage": "main_imports", "error": "Internal server error"})

    # Test workflow_config_models
    try:
        from workflow_config_models import create_workflow_config_models
        from database import Base
        workflow_models = create_workflow_config_models(Base)
        results["workflow_config_imports"]["WorkflowConfiguration"] = str(type(workflow_models.get('WorkflowConfiguration')))
        results["workflow_config_imports"]["WorkflowDayConfig"] = str(type(workflow_models.get('WorkflowDayConfig')))
        results["workflow_config_imports"]["WorkflowTaskInstance"] = str(type(workflow_models.get('WorkflowTaskInstance')))
    except Exception as e:
        results["errors"].append({"stage": "workflow_config_imports", "error": "Internal server error"})

    # Test models.user_onboarding
    try:
        from models.user_onboarding import Role
        results["main_imports"]["Role"] = str(type(Role))
    except Exception as e:
        results["errors"].append({"stage": "role_import", "error": "Internal server error"})

    # Test TaskGeneratorService
    try:
        from services.workflow_task_generator import TaskGeneratorService
        generator = TaskGeneratorService(db)
        results["service_init"]["TaskGeneratorService"] = "success"
    except Exception as e:
        import traceback
        results["errors"].append({
            "stage": "TaskGeneratorService",
            "error": "Internal server error"
        })

    # Test WorkflowSLAService
    try:
        from services.workflow_sla_service import WorkflowSLAService
        service = WorkflowSLAService(db)
        results["service_init"]["WorkflowSLAService"] = "success"
    except Exception as e:
        import traceback
        results["errors"].append({
            "stage": "WorkflowSLAService",
            "error": "Internal server error"
        })

    return results


# =============================================================================
# DIAGNOSTIC ENDPOINTS (AUTH REQUIRED FOR TENANT ISOLATION)
# =============================================================================

@router.get("/diagnostic/instance/{instance_id}")
async def workflow_instance_diagnostic(
    instance_id: int,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Diagnostic endpoint - shows why tasks are/aren't generating.
    Requires authentication for tenant isolation.
    """
    from sqlalchemy import text
    from datetime import datetime, timezone

    results = {
        "instance_id": instance_id,
        "instance": None,
        "workflow_config": None,
        "day_configs": [],
        "generation_analysis": [],
        "issues_found": [],
        "recommendations": []
    }

    try:
        # Get workflow instance - check all possible column names
        instance_query = db.execute(text("""
            SELECT
                id,
                organization_id,
                workflow_type,
                workflow_config_id,
                workflow_configuration_id,
                lead_id,
                loan_id,
                status,
                current_day,
                started_at,
                trigger_milestone_entered_at,
                last_task_generated_day,
                next_task_due_at,
                created_at
            FROM workflow_instances
            WHERE id = :id AND organization_id = :org_id
        """), {"id": instance_id, "org_id": current_user.organization_id}).fetchone()

        if not instance_query:
            return {"error": f"Workflow instance {instance_id} not found", "issues_found": ["Instance does not exist"]}

        # Parse instance data
        instance_data = {
            "id": instance_query[0],
            "organization_id": instance_query[1],
            "workflow_type": instance_query[2],
            "workflow_config_id": instance_query[3],
            "workflow_configuration_id": instance_query[4],
            "lead_id": instance_query[5],
            "loan_id": instance_query[6],
            "status": instance_query[7],
            "current_day": instance_query[8],
            "started_at": str(instance_query[9]) if instance_query[9] else None,
            "trigger_milestone_entered_at": str(instance_query[10]) if instance_query[10] else None,
            "last_task_generated_day": instance_query[11],
            "next_task_due_at": str(instance_query[12]) if instance_query[12] else None,
            "created_at": str(instance_query[13]) if instance_query[13] else None
        }
        results["instance"] = instance_data

        # Check for column mismatch issue
        config_id = instance_data["workflow_configuration_id"] or instance_data["workflow_config_id"]
        if instance_data["workflow_configuration_id"] is None and instance_data["workflow_config_id"] is not None:
            results["issues_found"].append("COLUMN_MISMATCH: workflow_configuration_id is NULL but workflow_config_id has value")
            results["recommendations"].append("Run: UPDATE workflow_instances SET workflow_configuration_id = workflow_config_id WHERE id = " + str(instance_id))

        if config_id is None:
            results["issues_found"].append("NO_WORKFLOW_CONFIG: Both workflow_configuration_id and workflow_config_id are NULL")
            results["recommendations"].append("Re-enroll lead/loan in workflow")
            return results

        # Calculate days elapsed
        trigger_time = instance_query[10] or instance_query[9]  # trigger_milestone_entered_at or started_at
        if trigger_time:
            now = datetime.now(timezone.utc)
            if trigger_time.tzinfo is None:
                trigger_time = trigger_time.replace(tzinfo=timezone.utc)
            days_elapsed = (now - trigger_time).days
            results["instance"]["days_elapsed"] = days_elapsed
        else:
            days_elapsed = 0
            results["issues_found"].append("NO_START_TIME: Neither trigger_milestone_entered_at nor started_at is set")

        # Get workflow configuration
        config_query = db.execute(text("""
            SELECT id, workflow_key, workflow_name, is_active
            FROM workflow_configurations
            WHERE id = :id AND (organization_id = :org_id OR organization_id IS NULL)
        """), {"id": config_id, "org_id": current_user.organization_id}).fetchone()

        if not config_query:
            results["issues_found"].append(f"WORKFLOW_CONFIG_NOT_FOUND: No workflow_configurations record with id={config_id}")
            return results

        results["workflow_config"] = {
            "id": config_query[0],
            "workflow_key": config_query[1],
            "workflow_name": config_query[2],
            "is_active": config_query[3]
        }

        # Get day configs
        day_configs_query = db.execute(text("""
            SELECT
                id, day_label, day_order, day_value, is_active,
                phone_enabled, phone_am_enabled, phone_pm_enabled,
                text_enabled, text_am_enabled, text_pm_enabled,
                email_enabled, referral_partner_enabled,
                lo_responsible, jr_lo_responsible, production_asst_responsible,
                concierge_responsible, ai_responsible
            FROM workflow_day_configs
            WHERE workflow_id = :config_id
            ORDER BY day_order
        """), {"config_id": config_id}).fetchall()

        if not day_configs_query:
            results["issues_found"].append(f"NO_DAY_CONFIGS: workflow_day_configs table has no records for workflow_id={config_id}")
            results["recommendations"].append("Run workflow seed: POST /api/v1/workflow-config/seed-defaults")
            return results

        last_generated = instance_data["last_task_generated_day"] or 0

        for row in day_configs_query:
            day_config = {
                "id": row[0],
                "day_label": row[1],
                "day_order": row[2],
                "day_value": row[3],
                "is_active": row[4],
                "phone_enabled": row[5],
                "phone_am_enabled": row[6],
                "phone_pm_enabled": row[7],
                "text_enabled": row[8],
                "text_am_enabled": row[9],
                "text_pm_enabled": row[10],
                "email_enabled": row[11],
                "referral_partner_enabled": row[12]
            }

            # Count enabled task types
            enabled_types = []
            if row[5]: enabled_types.append("phone")
            if row[6]: enabled_types.append("phone_am")
            if row[7]: enabled_types.append("phone_pm")
            if row[8]: enabled_types.append("text")
            if row[9]: enabled_types.append("text_am")
            if row[10]: enabled_types.append("text_pm")
            if row[11]: enabled_types.append("email")
            if row[12]: enabled_types.append("referral_partner")

            day_config["enabled_task_types"] = enabled_types
            day_config["enabled_count"] = len(enabled_types)
            results["day_configs"].append(day_config)

            # Analyze generation status
            day_value = row[3] or 0
            analysis = {
                "day_label": row[1],
                "day_value": day_value,
                "should_generate": False,
                "reason": "",
                "enabled_types": enabled_types
            }

            if not row[4]:  # is_active
                analysis["reason"] = "SKIPPED: Day config is not active"
            elif day_value <= last_generated:
                analysis["reason"] = f"SKIPPED: Already generated (day_value={day_value} <= last_generated={last_generated})"
            elif day_value > days_elapsed:
                analysis["reason"] = f"NOT_DUE: Day not yet due (day_value={day_value} > days_elapsed={days_elapsed})"
            elif len(enabled_types) == 0:
                analysis["reason"] = "SKIPPED: No task types enabled for this day"
                results["issues_found"].append(f"Day {row[1]} has no enabled task types")
            else:
                analysis["should_generate"] = True
                analysis["reason"] = f"SHOULD_GENERATE: Due and has {len(enabled_types)} enabled types"

            results["generation_analysis"].append(analysis)

        # Count existing tasks
        task_count = db.execute(text("""
            SELECT COUNT(*) FROM workflow_task_instances
            WHERE workflow_instance_id = :id AND organization_id = :org_id
        """), {"id": instance_id, "org_id": current_user.organization_id}).scalar()

        results["existing_task_count"] = task_count

        # Summary
        should_generate_count = len([a for a in results["generation_analysis"] if a["should_generate"]])
        results["summary"] = {
            "total_day_configs": len(day_configs_query),
            "days_should_generate": should_generate_count,
            "days_elapsed": days_elapsed,
            "last_task_generated_day": last_generated,
            "existing_tasks": task_count,
            "issues_count": len(results["issues_found"])
        }

        if should_generate_count == 0 and len(results["issues_found"]) == 0:
            if days_elapsed < 1:
                results["issues_found"].append(f"TOO_EARLY: Workflow started less than 1 day ago (days_elapsed={days_elapsed})")
                results["recommendations"].append("Wait until Day 1 is due, or backdate trigger_milestone_entered_at for testing")
            elif all(a["reason"].startswith("SKIPPED: Already generated") for a in results["generation_analysis"] if a["day_value"] <= days_elapsed):
                results["issues_found"].append("ALL_GENERATED: All due days have already been generated")

        return results

    except Exception as e:
        import traceback
        return {
            "error": "Internal server error",
            "instance_id": instance_id
        }


@router.post("/init/fix-day-semantics")
async def fix_workflow_day_semantics(
    backdate_instance_id: Optional[int] = Query(None, description="Instance ID to backdate for testing"),
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Fix workflow day semantics - changes 'First 24 Hours' from day_value=1 to day_value=0.

    This fixes a semantic design flaw where "First 24 Hours" was firing AFTER 24 hours
    instead of immediately upon enrollment.

    Optionally backdates a test instance for immediate task generation.

    Requires authentication for tenant isolation.
    """
    from sqlalchemy import text
    from datetime import datetime, timezone

    results = {
        "success": True,
        "before_state": [],
        "after_state": [],
        "rows_updated": 0,
        "instance_backdated": False,
        "errors": []
    }

    try:
        # Step 1: Capture before state
        before_query = db.execute(text("""
            SELECT
                wc.workflow_name as workflow_name,
                wdc.id as config_id,
                wdc.day_value,
                wdc.day_label
            FROM workflow_day_configs wdc
            JOIN workflow_configurations wc ON wdc.workflow_id = wc.id
            WHERE (wdc.day_label ILIKE '%24 Hour%'
               OR wdc.day_label ILIKE '%First%'
               OR wdc.day_value IN (0, 1))
              AND (wc.organization_id = :org_id OR wc.organization_id IS NULL)
            ORDER BY wc.workflow_name, wdc.day_value
        """), {"org_id": current_user.organization_id})

        results["before_state"] = [
            {"workflow": row[0], "config_id": row[1], "day_value": row[2], "day_label": row[3]}
            for row in before_query
        ]

        # Step 2: Fix "First 24 Hours" to day_value=0
        # NOTE: workflow_day_configs has no organization_id; scoped via workflow_configurations parent
        fix_result = db.execute(text("""
            UPDATE workflow_day_configs
            SET day_value = 0,
                updated_at = CURRENT_TIMESTAMP
            WHERE (day_label ILIKE '%First 24 Hour%'
               OR day_label ILIKE '%First%24%Hour%')
              AND workflow_id IN (
                  SELECT id FROM workflow_configurations
                  WHERE organization_id = :org_id OR organization_id IS NULL
              )
        """), {"org_id": current_user.organization_id})
        db.commit()

        results["rows_updated"] = fix_result.rowcount

        # Step 3: Backdate instance if requested
        if backdate_instance_id:
            backdate_result = db.execute(text("""
                UPDATE workflow_instances
                SET trigger_milestone_entered_at = NOW() - INTERVAL '2 days',
                    last_task_generated_day = -1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
                  AND status = 'active'
                  AND organization_id = :org_id
            """), {"id": backdate_instance_id, "org_id": current_user.organization_id})
            db.commit()

            results["instance_backdated"] = backdate_result.rowcount > 0
            results["backdated_instance_id"] = backdate_instance_id

        # Step 4: Capture after state
        after_query = db.execute(text("""
            SELECT
                wc.workflow_name as workflow_name,
                wdc.id as config_id,
                wdc.day_value,
                wdc.day_label
            FROM workflow_day_configs wdc
            JOIN workflow_configurations wc ON wdc.workflow_id = wc.id
            WHERE (wdc.day_label ILIKE '%24 Hour%'
               OR wdc.day_label ILIKE '%First%'
               OR wdc.day_value IN (0, 1))
              AND (wc.organization_id = :org_id OR wc.organization_id IS NULL)
            ORDER BY wc.workflow_name, wdc.day_value
        """), {"org_id": current_user.organization_id})

        results["after_state"] = [
            {"workflow": row[0], "config_id": row[1], "day_value": row[2], "day_label": row[3]}
            for row in after_query
        ]

        # Step 5: Verification query
        if backdate_instance_id:
            instance_check = db.execute(text("""
                SELECT
                    id,
                    trigger_milestone_entered_at,
                    last_task_generated_day,
                    status,
                    NOW() - trigger_milestone_entered_at as time_elapsed
                FROM workflow_instances
                WHERE id = :id AND organization_id = :org_id
            """), {"id": backdate_instance_id, "org_id": current_user.organization_id}).fetchone()

            if instance_check:
                results["instance_details"] = {
                    "id": instance_check[0],
                    "trigger_milestone_entered_at": str(instance_check[1]),
                    "last_task_generated_day": instance_check[2],
                    "status": instance_check[3],
                    "time_elapsed": str(instance_check[4])
                }

        results["next_steps"] = [
            "1. Wait 5 min for scheduler OR call: POST /api/v1/workflow-sla/scheduler/generate-tasks",
            "2. Check diagnostic: GET /api/v1/workflow-sla/diagnostic/instance/" + str(backdate_instance_id or "{instance_id}"),
            "3. Verify tasks: SELECT * FROM workflow_task_instances WHERE workflow_instance_id = " + str(backdate_instance_id or "{instance_id}")
        ]

    except Exception as e:
        import traceback
        logger.error(f"SLA migration error: {traceback.format_exc()}")
        results["success"] = False
        results["errors"].append("Migration error — check server logs")
        db.rollback()

    return results


@router.post("/init/generate-tasks")
async def generate_tasks_public(
    instance_id: Optional[int] = Query(None, description="Specific instance ID to generate tasks for"),
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Generate tasks for workflow instances.
    If instance_id provided, generates for that instance only.
    Otherwise generates for all active instances in the user's org.

    Requires authentication for tenant isolation.
    """
    from sqlalchemy import text
    from datetime import datetime, timezone

    results = {
        "success": True,
        "instances_processed": 0,
        "tasks_generated": 0,
        "details": [],
        "errors": []
    }

    try:
        # Get instances to process
        if instance_id:
            instances = db.execute(text("""
                SELECT
                    wi.id, wi.workflow_configuration_id, wi.lead_id, wi.loan_id,
                    wi.trigger_milestone_entered_at, wi.last_task_generated_day,
                    wi.organization_id
                FROM workflow_instances wi
                WHERE wi.id = :id AND wi.status = 'active'
                  AND wi.organization_id = :org_id
            """), {"id": instance_id, "org_id": current_user.organization_id}).fetchall()
        else:
            instances = db.execute(text("""
                SELECT
                    wi.id, wi.workflow_configuration_id, wi.lead_id, wi.loan_id,
                    wi.trigger_milestone_entered_at, wi.last_task_generated_day,
                    wi.organization_id
                FROM workflow_instances wi
                WHERE wi.status = 'active'
                  AND wi.organization_id = :org_id
            """), {"org_id": current_user.organization_id}).fetchall()

        for inst in instances:
            inst_id = inst[0]
            config_id = inst[1]
            lead_id = inst[2]
            loan_id = inst[3]
            trigger_time = inst[4]
            last_generated = inst[5] or -1
            org_id = inst[6]

            if not config_id:
                results["errors"].append(f"Instance {inst_id}: No workflow_configuration_id")
                continue

            # Calculate days elapsed
            if trigger_time:
                now = datetime.now(timezone.utc)
                if trigger_time.tzinfo is None:
                    trigger_time = trigger_time.replace(tzinfo=timezone.utc)
                days_elapsed = (now - trigger_time).days
            else:
                days_elapsed = 0

            # Get eligible day configs
            day_configs = db.execute(text("""
                SELECT id, day_value, day_label,
                       phone_enabled, email_enabled, text_enabled,
                       task_description
                FROM workflow_day_configs
                WHERE workflow_id = :config_id
                  AND is_active = true
                  AND day_value <= :days_elapsed
                  AND day_value > :last_generated
                ORDER BY day_value
            """), {
                "config_id": config_id,
                "days_elapsed": days_elapsed,
                "last_generated": last_generated
            }).fetchall()

            instance_tasks = 0
            max_day_generated = last_generated

            for dc in day_configs:
                dc_id = dc[0]
                day_value = dc[1]
                day_label = dc[2]
                phone = dc[3]
                email = dc[4]
                text_enabled = dc[5]
                description = dc[6] or day_label

                task_types = []
                if phone: task_types.append("phone")
                if email: task_types.append("email")
                if text_enabled: task_types.append("text")

                for task_type in task_types:
                    # Create task instance
                    db.execute(text("""
                        INSERT INTO workflow_task_instances (
                            workflow_instance_id, workflow_id, day_config_id,
                            organization_id, task_type, task_name, task_description,
                            day_number, status, lead_id, loan_id,
                            scheduled_date, due_date, created_at, updated_at
                        ) VALUES (
                            :instance_id, :workflow_id, :day_config_id,
                            :org_id, :task_type, :task_name, :task_description,
                            :day_number, 'pending', :lead_id, :loan_id,
                            NOW(), NOW() + INTERVAL '1 day', NOW(), NOW()
                        )
                    """), {
                        "instance_id": inst_id,
                        "workflow_id": config_id,
                        "day_config_id": dc_id,
                        "org_id": org_id,
                        "task_type": task_type,
                        "task_name": f"{day_label} - {task_type.title()}",
                        "task_description": description,
                        "day_number": day_value,
                        "lead_id": lead_id,
                        "loan_id": loan_id
                    })
                    instance_tasks += 1

                if day_value > max_day_generated:
                    max_day_generated = day_value

            # Update last_task_generated_day
            if max_day_generated > last_generated:
                db.execute(text("""
                    UPDATE workflow_instances
                    SET last_task_generated_day = :day, updated_at = NOW()
                    WHERE id = :id AND organization_id = :org_id
                """), {"day": max_day_generated, "id": inst_id, "org_id": current_user.organization_id})

            db.commit()

            results["instances_processed"] += 1
            results["tasks_generated"] += instance_tasks
            results["details"].append({
                "instance_id": inst_id,
                "days_elapsed": days_elapsed,
                "tasks_created": instance_tasks,
                "max_day_generated": max_day_generated
            })

    except SQLAlchemyError as e:
        import traceback
        logger.error(f"SLA DB migration error: {traceback.format_exc()}")
        results["success"] = False
        results["errors"].append("Database error — check server logs")
        db.rollback()

    return results


@router.get("/init/verify-day-semantics")
async def verify_day_semantics(
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Verify the day semantics fix was applied correctly.
    Shows all day configs and their current values.

    Requires authentication for tenant isolation.
    """
    from sqlalchemy import text

    try:
        # Get all day configs (workflow_day_configs has no org_id; scoped via workflow_configurations)
        configs = db.execute(text("""
            SELECT
                wc.workflow_name as workflow_name,
                wdc.day_value,
                wdc.day_label,
                wdc.phone_enabled,
                wdc.email_enabled,
                wdc.text_enabled
            FROM workflow_day_configs wdc
            JOIN workflow_configurations wc ON wdc.workflow_id = wc.id
            WHERE wc.organization_id = :org_id OR wc.organization_id IS NULL
            ORDER BY wc.workflow_name, wdc.day_value
        """), {"org_id": current_user.organization_id})

        by_workflow = {}
        for row in configs:
            wf_name = row[0]
            if wf_name not in by_workflow:
                by_workflow[wf_name] = []

            channels = []
            if row[3]: channels.append("phone")
            if row[4]: channels.append("email")
            if row[5]: channels.append("text")

            by_workflow[wf_name].append({
                "day_value": row[1],
                "day_label": row[2],
                "channels": channels
            })

        # Check for issues
        issues = []
        for wf_name, days in by_workflow.items():
            for day in days:
                if "First 24" in day["day_label"] and day["day_value"] != 0:
                    issues.append(f"{wf_name}: '{day['day_label']}' should be day_value=0, but is {day['day_value']}")

        return {
            "workflows": by_workflow,
            "issues": issues,
            "is_correct": len(issues) == 0
        }

    except Exception as e:
        import traceback
        return {"error": "Internal server error"}


@router.get("/diagnostic/summary")
async def workflow_diagnostic_summary(
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Diagnostic endpoint - shows overall workflow system health.
    Requires authentication for tenant isolation.
    """
    from sqlalchemy import text

    try:
        # Count tables
        summary = {}

        # Workflow instances by status
        instances = db.execute(text("""
            SELECT status, COUNT(*) as count
            FROM workflow_instances
            WHERE organization_id = :org_id
            GROUP BY status
        """), {"org_id": current_user.organization_id}).fetchall()
        summary["workflow_instances"] = {row[0]: row[1] for row in instances}
        summary["total_instances"] = sum(row[1] for row in instances)

        # Workflow configurations
        configs = db.execute(text("""
            SELECT COUNT(*) FROM workflow_configurations
            WHERE organization_id = :org_id OR organization_id IS NULL
        """), {"org_id": current_user.organization_id}).scalar()
        summary["workflow_configurations"] = configs

        # Day configs — scoped via workflow_configurations parent
        day_configs = db.execute(text("""
            SELECT COUNT(*) FROM workflow_day_configs wdc
            JOIN workflow_configurations wc ON wdc.workflow_id = wc.id
            WHERE wc.organization_id = :org_id OR wc.organization_id IS NULL
        """), {"org_id": current_user.organization_id}).scalar()
        summary["workflow_day_configs"] = day_configs

        # Task instances
        tasks = db.execute(text("""
            SELECT status, COUNT(*) as count
            FROM workflow_task_instances
            WHERE organization_id = :org_id
            GROUP BY status
        """), {"org_id": current_user.organization_id}).fetchall()
        summary["workflow_task_instances"] = {row[0]: row[1] for row in tasks} if tasks else {}
        summary["total_tasks"] = sum(row[1] for row in tasks) if tasks else 0

        # Recent task generation
        recent = db.execute(text("""
            SELECT id, workflow_instance_id, task_type, status, created_at
            FROM workflow_task_instances
            WHERE organization_id = :org_id
            ORDER BY created_at DESC
            LIMIT 5
        """), {"org_id": current_user.organization_id}).fetchall()
        summary["recent_tasks"] = [
            {"id": r[0], "instance_id": r[1], "type": r[2], "status": r[3], "created": str(r[4])}
            for r in recent
        ] if recent else []

        # Potential issues
        issues = []

        if configs == 0:
            issues.append("NO_WORKFLOW_CONFIGS: No workflow configurations exist - run seed")
        if day_configs == 0:
            issues.append("NO_DAY_CONFIGS: No workflow day configs exist - run seed")
        if summary["total_instances"] > 0 and summary["total_tasks"] == 0:
            issues.append("NO_TASKS_GENERATED: Active instances exist but no tasks have been generated")

        summary["issues"] = issues

        # Check linked tasks in main tasks table
        linked_tasks = db.execute(text("""
            SELECT COUNT(*) FROM tasks
            WHERE workflow_task_instance_id IS NOT NULL
              AND organization_id = :org_id
        """), {"org_id": current_user.organization_id}).scalar() or 0
        summary["linked_tasks_in_main_table"] = linked_tasks

        return summary

    except SQLAlchemyError as e:
        import traceback
        return {"error": "Internal server error"}


@router.post("/diagnostic/test-linked-task")
async def test_create_linked_task(
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Test creating a linked task using EXACT same INSERT as _create_linked_task.
    This helps debug why linked tasks aren't being created.
    Requires authentication for tenant isolation.
    """
    from sqlalchemy import text
    import traceback

    try:
        # Use EXACT same INSERT as _create_linked_task in workflow_task_generator.py
        db.execute(text("""
            INSERT INTO tasks (
                title, description, status, priority,
                due_date, owner_id, lead_id, loan_id,
                related_contact_name, related_type,
                workflow_task_instance_id, task_group_key,
                organization_id,
                created_at, updated_at
            ) VALUES (
                :title, :description, 'pending', :priority,
                :due_date, :owner_id, :lead_id, :loan_id,
                :contact_name, :related_type,
                :task_instance_id, :group_key,
                :org_id,
                NOW(), NOW()
            )
        """), {
            "title": "[TEST] Workflow Task",
            "description": "Test task to debug linked task creation",
            "priority": "medium",
            "due_date": "2025-12-28",
            "owner_id": current_user.id,
            "lead_id": None,
            "loan_id": None,
            "contact_name": "Test Contact",
            "related_type": "lead",
            "task_instance_id": -999,
            "group_key": "test_group_diagnostic",
            "org_id": current_user.organization_id
        })
        db.commit()

        # Check if it was created
        result = db.execute(text("""
            SELECT id, title, workflow_task_instance_id
            FROM tasks
            WHERE workflow_task_instance_id = -999
              AND organization_id = :org_id
        """), {"org_id": current_user.organization_id}).fetchone()

        if result:
            # Clean up
            db.execute(text("DELETE FROM tasks WHERE id = :id AND organization_id = :org_id"), {"id": result[0], "org_id": current_user.organization_id})
            db.commit()
            return {
                "success": True,
                "message": "Linked task creation works!",
                "test_task_id": result[0]
            }
        else:
            return {
                "success": False,
                "message": "Task was not found after insert"
            }

    except SQLAlchemyError as e:
        db.rollback()
        return {
            "success": False,
            "error": "Internal server error"
        }


@router.get("/diagnostic/linked-tasks")
async def get_linked_tasks_diagnostic(
    limit: int = Query(20, le=100),
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Check linked tasks in the main tasks table.
    Shows workflow tasks that appear in the task list UI.
    Requires authentication for tenant isolation.
    """
    from sqlalchemy import text

    try:
        # Get tasks with workflow links
        linked = db.execute(text("""
            SELECT t.id, t.title, t.status, t.priority, t.due_date,
                   t.owner_id, t.lead_id, t.loan_id,
                   t.workflow_task_instance_id, t.task_group_key,
                   t.created_at
            FROM tasks t
            WHERE t.workflow_task_instance_id IS NOT NULL
              AND t.organization_id = :org_id
            ORDER BY t.created_at DESC
            LIMIT :limit
        """), {"limit": limit, "org_id": current_user.organization_id}).fetchall()

        tasks = [
            {
                "id": r[0],
                "title": r[1],
                "status": r[2],
                "priority": r[3],
                "due_date": str(r[4]) if r[4] else None,
                "owner_id": r[5],
                "lead_id": r[6],
                "loan_id": r[7],
                "workflow_task_instance_id": r[8],
                "task_group_key": r[9],
                "created_at": str(r[10])
            }
            for r in linked
        ]

        # Count total
        total = db.execute(text("""
            SELECT COUNT(*) FROM tasks
            WHERE workflow_task_instance_id IS NOT NULL
        """)).scalar() or 0

        return {
            "total_linked_tasks": total,
            "tasks": tasks
        }

    except SQLAlchemyError as e:
        import traceback
        return {"error": "Internal server error"}


@router.get("/diagnostic/task-instance-data/{instance_id}")
async def get_task_instance_data(
    instance_id: int,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Debug endpoint to see what data is available for a workflow task instance.
    Shows the data that would be passed to _create_linked_task.
    Requires authentication for tenant isolation.
    """
    from sqlalchemy import text

    try:
        # Get workflow task instance
        task_instance = db.execute(text("""
            SELECT wti.id, wti.workflow_instance_id, wti.day_config_id,
                   wti.task_type, wti.scheduled_date, wti.status,
                   wti.assigned_user_id, wti.linked_task_id, wti.route
            FROM workflow_task_instances wti
            WHERE wti.id = :id AND wti.organization_id = :org_id
        """), {"id": instance_id, "org_id": current_user.organization_id}).fetchone()

        if not task_instance:
            return {"error": f"Task instance {instance_id} not found"}

        # Get workflow instance
        workflow_instance = db.execute(text("""
            SELECT wi.id, wi.lead_id, wi.loan_id, wi.organization_id, wi.started_at
            FROM workflow_instances wi
            WHERE wi.id = :id AND wi.organization_id = :org_id
        """), {"id": task_instance[1], "org_id": current_user.organization_id}).fetchone()

        # Get day config
        # NOTE: workflow_day_configs has no organization_id column; scoped via parent workflow_configurations
        day_config = db.execute(text("""
            SELECT wdc.id, wdc.day_label, wdc.day_value, wdc.task_description
            FROM workflow_day_configs wdc
            JOIN workflow_configurations wc ON wdc.workflow_id = wc.id
            WHERE wdc.id = :id AND (wc.organization_id = :org_id OR wc.organization_id IS NULL)
        """), {"id": task_instance[2], "org_id": current_user.organization_id}).fetchone()

        # Get contact info and lead owner
        contact_info = {}
        lead_owner_id = None
        loan_officer_id = None
        if workflow_instance and workflow_instance[1]:  # lead_id
            lead = db.execute(text("""
                SELECT first_name, last_name, email, phone, owner_id
                FROM leads WHERE id = :id AND organization_id = :org_id
            """), {"id": workflow_instance[1], "org_id": current_user.organization_id}).fetchone()
            if lead:
                contact_info = {
                    "name": f"{lead[0] or ''} {lead[1] or ''}".strip(),
                    "email": lead[2],
                    "phone": lead[3]
                }
                lead_owner_id = lead[4]

        if workflow_instance and workflow_instance[2]:  # loan_id
            loan = db.execute(text("""
                SELECT loan_officer_id FROM loans WHERE id = :id AND organization_id = :org_id
            """), {"id": workflow_instance[2], "org_id": current_user.organization_id}).fetchone()
            if loan:
                loan_officer_id = loan[0]

        return {
            "task_instance": {
                "id": task_instance[0],
                "workflow_instance_id": task_instance[1],
                "day_config_id": task_instance[2],
                "task_type": task_instance[3],
                "scheduled_date": str(task_instance[4]) if task_instance[4] else None,
                "status": task_instance[5],
                "assigned_user_id": task_instance[6],
                "linked_task_id": task_instance[7],
                "route": task_instance[8]
            },
            "workflow_instance": {
                "id": workflow_instance[0] if workflow_instance else None,
                "lead_id": workflow_instance[1] if workflow_instance else None,
                "loan_id": workflow_instance[2] if workflow_instance else None,
                "organization_id": workflow_instance[3] if workflow_instance else None,
                "started_at": str(workflow_instance[4]) if workflow_instance and workflow_instance[4] else None
            } if workflow_instance else None,
            "day_config": {
                "id": day_config[0] if day_config else None,
                "day_label": day_config[1] if day_config else None,
                "day_value": day_config[2] if day_config else None,
                "task_description": day_config[3] if day_config else None
            } if day_config else None,
            "contact_info": contact_info,
            "lead_owner_id": lead_owner_id,
            "loan_officer_id": loan_officer_id,
            "resolved_owner_id": lead_owner_id or loan_officer_id,
            "can_create_linked_task": {
                "has_assigned_user": task_instance[6] is not None,
                "has_workflow_instance": workflow_instance is not None,
                "has_day_config": day_config is not None,
                "has_lead_or_loan": (workflow_instance[1] if workflow_instance else None) is not None or
                                   (workflow_instance[2] if workflow_instance else None) is not None,
                "has_owner": (lead_owner_id or loan_officer_id) is not None
            }
        }

    except Exception as e:
        import traceback
        return {"error": "Internal server error"}


@router.post("/init/create-missing-linked-tasks")
async def create_missing_linked_tasks(
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create linked tasks in the main tasks table for all workflow task instances
    that don't have a linked_task_id yet.
    Requires authentication for tenant isolation.
    """
    from sqlalchemy import text

    try:
        # Get all workflow task instances without linked tasks (scoped to current org)
        instances = db.execute(text("""
            SELECT wti.id, wti.workflow_instance_id, wti.day_config_id,
                   wti.task_type, wti.scheduled_date, wti.assigned_user_id,
                   wi.lead_id, wi.loan_id,
                   wdc.day_label, wdc.day_value, wdc.task_description
            FROM workflow_task_instances wti
            JOIN workflow_instances wi ON wi.id = wti.workflow_instance_id
            JOIN workflow_day_configs wdc ON wdc.id = wti.day_config_id
            WHERE wti.linked_task_id IS NULL
              AND wi.organization_id = :org_id
        """), {"org_id": current_user.organization_id}).fetchall()

        created = 0
        skipped = 0
        errors = []

        for inst in instances:
            task_instance_id = inst[0]
            lead_id = inst[6]
            loan_id = inst[7]
            task_type = inst[3]
            scheduled_date = inst[4]
            assigned_user_id = inst[5]
            day_label = inst[8]
            day_value = inst[9]
            task_description = inst[10]

            # Get owner_id
            owner_id = assigned_user_id
            if not owner_id and lead_id:
                lead = db.execute(text("SELECT owner_id FROM leads WHERE id = :id AND organization_id = :org_id"), {"id": lead_id, "org_id": current_user.organization_id}).fetchone()
                if lead and lead[0]:
                    owner_id = lead[0]
            if not owner_id and loan_id:
                loan = db.execute(text("SELECT loan_officer_id FROM loans WHERE id = :id AND organization_id = :org_id"), {"id": loan_id, "org_id": current_user.organization_id}).fetchone()
                if loan and loan[0]:
                    owner_id = loan[0]

            if not owner_id:
                skipped += 1
                continue

            # Get contact name
            contact_name = "Contact"
            if lead_id:
                lead = db.execute(text("SELECT first_name, last_name FROM leads WHERE id = :id AND organization_id = :org_id"), {"id": lead_id, "org_id": current_user.organization_id}).fetchone()
                if lead:
                    contact_name = f"{lead[0] or ''} {lead[1] or ''}".strip() or "Contact"

            # Build title and description
            title = f"[Workflow] {task_type.replace('_', ' ').title()} - {contact_name}"
            description = f"Workflow Task: {day_label}\n{task_description or ''}"

            # Determine priority
            priority = 'medium'
            if day_value is not None:
                if day_value <= 1:
                    priority = 'high'
                elif day_value >= 30:
                    priority = 'low'

            try:
                # Insert linked task
                db.execute(text("""
                    INSERT INTO tasks (
                        title, description, status, priority,
                        due_date, owner_id, lead_id, loan_id,
                        related_contact_name, related_type,
                        workflow_task_instance_id,
                        created_at, updated_at
                    ) VALUES (
                        :title, :description, 'pending', :priority,
                        :due_date, :owner_id, :lead_id, :loan_id,
                        :contact_name, :related_type,
                        :task_instance_id,
                        NOW(), NOW()
                    )
                """), {
                    "title": title,
                    "description": description,
                    "priority": priority,
                    "due_date": scheduled_date,
                    "owner_id": owner_id,
                    "lead_id": lead_id,
                    "loan_id": loan_id,
                    "contact_name": contact_name,
                    "related_type": 'lead' if lead_id else 'loan',
                    "task_instance_id": task_instance_id
                })

                # Get the new task ID
                result = db.execute(text("""
                    SELECT id FROM tasks WHERE workflow_task_instance_id = :id AND organization_id = :org_id ORDER BY id DESC LIMIT 1
                """), {"id": task_instance_id, "org_id": current_user.organization_id}).fetchone()

                if result:
                    # Update the workflow task instance with the linked task ID
                    db.execute(text("""
                        UPDATE workflow_task_instances SET linked_task_id = :task_id WHERE id = :id AND organization_id = :org_id
                    """), {"task_id": result[0], "id": task_instance_id, "org_id": current_user.organization_id})
                    created += 1

            except SQLAlchemyError as e:
                errors.append({"task_instance_id": task_instance_id, "error": "Internal server error"})

        db.commit()

        return {
            "success": True,
            "created": created,
            "skipped": skipped,
            "errors": errors
        }

    except SQLAlchemyError as e:
        db.rollback()
        import traceback
        return {"success": False, "error": "Internal server error"}


@router.post("/test/create-workflow-instance")
async def test_create_workflow_instance(
    lead_id: int = Query(..., description="Lead ID to enroll"),
    workflow_key: str = Query("prospect", description="Workflow key (prospect, prequal, etc.)"),
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    TEST ENDPOINT: Create a new workflow instance and generate tasks.
    Verifies the complete workflow → task → linked task flow.
    Requires authentication for tenant isolation.
    """
    from sqlalchemy import text
    from datetime import datetime, timezone
    import traceback

    results = {
        "success": False,
        "workflow_instance_id": None,
        "tasks_generated": 0,
        "linked_tasks_created": 0,
        "steps": []
    }

    try:
        # Step 1: Verify lead exists and get owner
        lead = db.execute(text("""
            SELECT id, name, owner_id FROM leads WHERE id = :id AND organization_id = :org_id
        """), {"id": lead_id, "org_id": current_user.organization_id}).fetchone()

        if not lead:
            return {"success": False, "error": f"Lead {lead_id} not found"}

        results["steps"].append(f"1. Found lead: {lead[1]} (owner_id={lead[2]})")

        # Step 2: Get workflow configuration
        config = db.execute(text("""
            SELECT id, workflow_key, workflow_name
            FROM workflow_configurations
            WHERE workflow_key = :key AND is_active = true
              AND (organization_id = :org_id OR organization_id IS NULL)
            LIMIT 1
        """), {"key": workflow_key, "org_id": current_user.organization_id}).fetchone()

        if not config:
            return {"success": False, "error": f"Workflow '{workflow_key}' not found"}

        results["steps"].append(f"2. Found workflow config: {config[2]} (id={config[0]})")

        # Step 3: Create workflow instance
        db.execute(text("""
            INSERT INTO workflow_instances (
                organization_id, workflow_configuration_id, lead_id,
                workflow_type, status, started_at, trigger_milestone_entered_at,
                last_task_generated_day, created_at
            ) VALUES (
                :org_id, :config_id, :lead_id,
                :workflow_key, 'active', NOW(), NOW(),
                -1, NOW()
            )
        """), {"org_id": current_user.organization_id, "config_id": config[0], "lead_id": lead_id, "workflow_key": workflow_key})
        db.flush()

        # Get the new instance ID
        instance = db.execute(text("""
            SELECT id FROM workflow_instances
            WHERE lead_id = :lead_id AND workflow_configuration_id = :config_id
              AND organization_id = :org_id
            ORDER BY id DESC LIMIT 1
        """), {"lead_id": lead_id, "config_id": config[0], "org_id": current_user.organization_id}).fetchone()

        if not instance:
            return {"success": False, "error": "Failed to create workflow instance"}

        instance_id = instance[0]
        results["workflow_instance_id"] = instance_id
        results["steps"].append(f"3. Created workflow instance: {instance_id}")

        db.commit()

        # Step 4: Generate tasks using the TaskGeneratorService
        from services.workflow_task_generator import TaskGeneratorService
        generator = TaskGeneratorService(db)
        gen_result = generator.generate_tasks_for_instance(instance_id, force_regenerate=True)

        results["tasks_generated"] = gen_result.get("tasks_created", 0)
        results["gen_result"] = gen_result  # Full result for debugging
        results["steps"].append(f"4. Generated {results['tasks_generated']} workflow task instances")

        # Step 5: Check linked tasks created
        linked = db.execute(text("""
            SELECT COUNT(*) FROM tasks
            WHERE workflow_task_instance_id IN (
                SELECT id FROM workflow_task_instances
                WHERE workflow_instance_id = :id AND organization_id = :org_id
            )
            AND organization_id = :org_id
        """), {"id": instance_id, "org_id": current_user.organization_id}).scalar()

        results["linked_tasks_created"] = linked or 0
        results["steps"].append(f"5. Created {results['linked_tasks_created']} linked tasks in main table")

        # Step 6: Get sample task
        sample_task = db.execute(text("""
            SELECT t.id, t.title, t.owner_id, t.lead_id, t.workflow_task_instance_id
            FROM tasks t
            WHERE t.workflow_task_instance_id IN (
                SELECT id FROM workflow_task_instances
                WHERE workflow_instance_id = :id AND organization_id = :org_id
            )
            AND t.organization_id = :org_id
            LIMIT 1
        """), {"id": instance_id, "org_id": current_user.organization_id}).fetchone()

        if sample_task:
            results["sample_linked_task"] = {
                "id": sample_task[0],
                "title": sample_task[1],
                "owner_id": sample_task[2],
                "lead_id": sample_task[3],
                "workflow_task_instance_id": sample_task[4]
            }

        results["success"] = True
        return results

    except Exception as e:
        db.rollback()
        return {
            "success": False,
            "error": "Internal server error",
            "steps": results["steps"]
        }


@router.get("/diagnostic/tasks-for-user/{user_id}")
async def get_tasks_for_user_diagnostic(
    user_id: int,
    limit: int = Query(100, le=500),
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Debug endpoint to check what tasks would appear for a specific user.
    This simulates the unified-tasks query.
    Requires authentication for tenant isolation.
    """
    from sqlalchemy import text

    try:
        # Get workflow tasks from main tasks table (same query as unified-tasks)
        tasks = db.execute(text("""
            SELECT t.id, t.title, t.status, t.priority, t.due_date,
                   t.owner_id, t.lead_id, t.loan_id,
                   t.workflow_task_instance_id,
                   t.related_contact_name, t.related_type
            FROM tasks t
            WHERE t.owner_id = :user_id
              AND t.status IN ('pending', 'in_progress')
              AND t.organization_id = :org_id
            ORDER BY t.due_date ASC
            LIMIT :limit
        """), {"user_id": user_id, "limit": limit, "org_id": current_user.organization_id}).fetchall()

        # Get user info
        user = db.execute(text("""
            SELECT id, email, full_name FROM users WHERE id = :id AND organization_id = :org_id
        """), {"id": user_id, "org_id": current_user.organization_id}).fetchone()

        workflow_tasks = [t for t in tasks if t[8] is not None]  # workflow_task_instance_id at index 8

        return {
            "user": {
                "id": user[0] if user else None,
                "email": user[1] if user else None,
                "name": user[2] if user else None
            } if user else None,
            "total_tasks": len(tasks),
            "workflow_tasks": len(workflow_tasks),
            "tasks": [
                {
                    "id": t[0],
                    "title": t[1],
                    "status": t[2],
                    "priority": t[3],
                    "due_date": str(t[4]) if t[4] else None,
                    "lead_id": t[6],
                    "loan_id": t[7],
                    "workflow_task_instance_id": t[8],
                    "contact_name": t[9],
                    "is_workflow_task": t[8] is not None
                }
                for t in tasks
            ]
        }

    except Exception as e:
        import traceback
        return {"error": "Internal server error"}


@router.delete("/test/cleanup-test-instances")
async def cleanup_test_workflow_instances(
    keep_count: int = Query(1, description="Number of instances to keep per lead"),
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Clean up test workflow instances, keeping only the specified number per lead.
    Also removes orphaned linked tasks.
    Requires authentication for tenant isolation.
    """
    from sqlalchemy import text
    import traceback

    try:
        results = {
            "instances_deleted": 0,
            "task_instances_deleted": 0,
            "linked_tasks_deleted": 0,
        }

        # Get instances to delete (keep only 'keep_count' per lead, ordered by created_at DESC)
        instances_to_delete = db.execute(text("""
            WITH ranked AS (
                SELECT id, lead_id, loan_id,
                       ROW_NUMBER() OVER (PARTITION BY COALESCE(lead_id, 0), COALESCE(loan_id, 0)
                                          ORDER BY created_at DESC) as rn
                FROM workflow_instances
                WHERE organization_id = :org_id
            )
            SELECT id FROM ranked WHERE rn > :keep_count
        """), {"keep_count": keep_count, "org_id": current_user.organization_id}).fetchall()

        instance_ids = [row[0] for row in instances_to_delete]

        if not instance_ids:
            return {"message": "No instances to clean up", **results}

        # Delete linked tasks first
        linked_deleted = db.execute(text("""
            DELETE FROM tasks
            WHERE workflow_task_instance_id IN (
                SELECT id FROM workflow_task_instances
                WHERE workflow_instance_id = ANY(:ids) AND organization_id = :org_id
            )
            AND organization_id = :org_id
        """), {"ids": instance_ids, "org_id": current_user.organization_id})
        results["linked_tasks_deleted"] = linked_deleted.rowcount

        # Delete workflow task instances
        task_instances_deleted = db.execute(text("""
            DELETE FROM workflow_task_instances
            WHERE workflow_instance_id = ANY(:ids) AND organization_id = :org_id
        """), {"ids": instance_ids, "org_id": current_user.organization_id})
        results["task_instances_deleted"] = task_instances_deleted.rowcount

        # Delete workflow instances
        instances_deleted = db.execute(text("""
            DELETE FROM workflow_instances
            WHERE id = ANY(:ids) AND organization_id = :org_id
        """), {"ids": instance_ids, "org_id": current_user.organization_id})
        results["instances_deleted"] = instances_deleted.rowcount

        db.commit()

        return {
            "success": True,
            "message": f"Cleaned up {results['instances_deleted']} workflow instances",
            **results
        }

    except SQLAlchemyError as e:
        db.rollback()
        return {
            "success": False,
            "error": "Internal server error"
        }


@router.get("/diagnostic/verify-unified-tasks/{user_id}")
async def verify_unified_tasks_for_user(
    user_id: int,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Verify what unified-tasks endpoint would return for a user.
    This mimics the exact query used by /api/v1/unified-tasks.
    Requires authentication for tenant isolation.
    """
    from sqlalchemy.orm import joinedload
    from database.models import Task

    try:
        # Same query as unified-tasks endpoint (with updated 200 limit)
        workflow_tasks = db.query(Task).filter(
            Task.owner_id == user_id,
            Task.organization_id == current_user.organization_id,
            Task.status.in_(["pending", "in_progress"])
        ).order_by(Task.due_date.asc()).limit(200).all()

        # Count workflow vs non-workflow tasks
        workflow_count = sum(1 for t in workflow_tasks if t.workflow_task_instance_id is not None)
        non_workflow_count = len(workflow_tasks) - workflow_count

        # Sample workflow tasks
        workflow_samples = [
            {
                "id": t.id,
                "title": t.title,
                "status": t.status,
                "due_date": str(t.due_date) if t.due_date else None,
                "lead_id": t.lead_id,
                "workflow_task_instance_id": t.workflow_task_instance_id
            }
            for t in workflow_tasks if t.workflow_task_instance_id is not None
        ][:10]

        return {
            "user_id": user_id,
            "total_tasks_fetched": len(workflow_tasks),
            "workflow_tasks_count": workflow_count,
            "non_workflow_tasks_count": non_workflow_count,
            "workflow_tasks_included": workflow_count > 0,
            "sample_workflow_tasks": workflow_samples,
            "message": f"Unified-tasks would return {workflow_count} workflow tasks out of {len(workflow_tasks)} total"
        }

    except Exception as e:
        import traceback
        return {"error": "Internal server error"}


# =============================================================================
# ADMIN - SALESFORCE SLA MIGRATION
# =============================================================================

@router.post("/admin/seed-salesforce-sla-workflows")
async def seed_salesforce_sla_workflows(
    admin_key: str = Header(..., alias="X-Admin-Key", description="Admin API key for authentication"),
    db: Session = Depends(get_db)
):
    """
    Seed Salesforce SLA workflow configurations.

    Creates workflow configurations for:
    - Closing countdown
    - Rate lock monitoring
    - Lock expiration alerts
    - Disclosure follow-up

    Requires admin_key for authentication.
    """
    import os

    # Verify admin key
    expected_key = os.getenv("ADMIN_API_KEY", "")
    if admin_key != expected_key:
        raise HTTPException(status_code=403, detail="Invalid admin key")

    try:
        from datetime import timezone
        now = datetime.now(timezone.utc)

        # Salesforce-triggered workflow configurations
        SALESFORCE_WORKFLOWS = [
            {
                "workflow_key": "closing",
                "workflow_name": "Closing Countdown",
                "description": "Tasks triggered when closing date is set from Salesforce.",
                "entity_type": "loan",
                "trigger_type": "salesforce_date",
                "trigger_field": "closing_date",
                "days": [
                    {"day_value": -14, "day_label": "14 Days to Closing", "phone_enabled": True, "email_enabled": True, "text_enabled": False, "task_description": "Review file for closing readiness."},
                    {"day_value": -7, "day_label": "7 Days to Closing", "phone_enabled": True, "email_enabled": True, "text_enabled": True, "task_description": "Confirm borrower has scheduled closing."},
                    {"day_value": -3, "day_label": "3 Days to Closing", "phone_enabled": True, "email_enabled": True, "text_enabled": True, "task_description": "Final closing confirmation."},
                    {"day_value": -1, "day_label": "1 Day to Closing", "phone_enabled": True, "email_enabled": False, "text_enabled": True, "task_description": "Day before closing confirmation."},
                    {"day_value": 0, "day_label": "Closing Day", "phone_enabled": True, "email_enabled": True, "text_enabled": False, "task_description": "Congratulate borrower."}
                ]
            },
            {
                "workflow_key": "rate_lock",
                "workflow_name": "Rate Lock Monitoring",
                "description": "Tasks triggered when rate is locked.",
                "entity_type": "loan",
                "trigger_type": "salesforce_date",
                "trigger_field": "lock_date",
                "days": [
                    {"day_value": 0, "day_label": "Rate Lock Confirmation", "phone_enabled": False, "email_enabled": True, "text_enabled": False, "task_description": "Send rate lock confirmation."},
                    {"day_value": 1, "day_label": "Rate Lock Follow-up", "phone_enabled": True, "email_enabled": False, "text_enabled": False, "task_description": "Confirm borrower received lock confirmation."}
                ]
            },
            {
                "workflow_key": "lock_expiration",
                "workflow_name": "Lock Expiration Countdown",
                "description": "Urgent countdown tasks before rate lock expires.",
                "entity_type": "loan",
                "trigger_type": "salesforce_date",
                "trigger_field": "lock_expiration_date",
                "days": [
                    {"day_value": -7, "day_label": "7 Days to Lock Expiration", "phone_enabled": True, "email_enabled": True, "text_enabled": False, "task_description": "ALERT: Lock expires in 7 days."},
                    {"day_value": -3, "day_label": "3 Days to Lock Expiration", "phone_enabled": True, "email_enabled": True, "text_enabled": True, "task_description": "URGENT: Lock expires in 3 days."},
                    {"day_value": -1, "day_label": "1 Day to Lock Expiration", "phone_enabled": True, "email_enabled": True, "text_enabled": True, "task_description": "CRITICAL: Lock expires tomorrow."}
                ]
            },
            {
                "workflow_key": "disclosure_sent",
                "workflow_name": "Post-Disclosure Follow-up",
                "description": "Follow-up sequence after initial disclosure is sent.",
                "entity_type": "loan",
                "trigger_type": "salesforce_date",
                "trigger_field": "disclosure_sent_date",
                "days": [
                    {"day_value": 1, "day_label": "Disclosure Follow-up", "phone_enabled": True, "email_enabled": True, "text_enabled": False, "task_description": "Follow up on disclosure receipt."},
                    {"day_value": 3, "day_label": "Disclosure Reminder", "phone_enabled": True, "email_enabled": True, "text_enabled": True, "task_description": "Reminder to sign disclosure."}
                ]
            }
        ]

        results = {"created": [], "skipped": [], "errors": []}

        from sqlalchemy import text

        for workflow in SALESFORCE_WORKFLOWS:
            try:
                # Check if workflow already exists
                existing = db.execute(text("""
                    SELECT id FROM workflow_configurations
                    WHERE workflow_key = :key
                """), {"key": workflow["workflow_key"]}).fetchone()

                if existing:
                    results["skipped"].append(workflow["workflow_key"])
                    continue

                # Create workflow configuration
                result = db.execute(text("""
                    INSERT INTO workflow_configurations (
                        workflow_key, workflow_name, description,
                        entity_type, trigger_type, trigger_field,
                        is_active, is_system_template,
                        created_at, updated_at
                    ) VALUES (
                        :workflow_key, :workflow_name, :description,
                        :entity_type, :trigger_type, :trigger_field,
                        true, true,
                        :now, :now
                    )
                    RETURNING id
                """), {
                    "workflow_key": workflow["workflow_key"],
                    "workflow_name": workflow["workflow_name"],
                    "description": workflow["description"],
                    "entity_type": workflow.get("entity_type", "loan"),
                    "trigger_type": workflow.get("trigger_type", "salesforce_date"),
                    "trigger_field": workflow.get("trigger_field"),
                    "now": now
                })
                workflow_id = result.fetchone()[0]

                # Create day configurations
                for day_idx, day_config in enumerate(workflow.get("days", []), start=1):
                    db.execute(text("""
                        INSERT INTO workflow_day_configs (
                            workflow_id, day_value, day_label, day_order,
                            phone_enabled, email_enabled, text_enabled,
                            task_description, is_active,
                            created_at, updated_at
                        ) VALUES (
                            :workflow_id, :day_value, :day_label, :day_order,
                            :phone_enabled, :email_enabled, :text_enabled,
                            :task_description, true,
                            :now, :now
                        )
                    """), {
                        "workflow_id": workflow_id,
                        "day_value": day_config["day_value"],
                        "day_label": day_config["day_label"],
                        "day_order": day_idx,
                        "phone_enabled": day_config.get("phone_enabled", False),
                        "email_enabled": day_config.get("email_enabled", True),
                        "text_enabled": day_config.get("text_enabled", False),
                        "task_description": day_config.get("task_description", ""),
                        "now": now
                    })

                results["created"].append({
                    "workflow_key": workflow["workflow_key"],
                    "workflow_id": workflow_id,
                    "days_created": len(workflow.get("days", []))
                })

            except Exception as e:
                results["errors"].append({
                    "workflow_key": workflow["workflow_key"],
                    "error": "Internal server error"
                })

        db.commit()

        return {
            "success": True,
            "message": f"Created {len(results['created'])} workflows, skipped {len(results['skipped'])}",
            "results": results
        }

    except SQLAlchemyError as e:
        db.rollback()
        import traceback
        raise HTTPException(
            status_code=500,
            detail="Migration failed: check server logs"
        )


@router.post("/admin/fix-salesforce-sla-day-configs")
async def fix_salesforce_sla_day_configs(
    admin_key: str = Header(..., alias="X-Admin-Key", description="Admin API key for authentication"),
    db: Session = Depends(get_db)
):
    """
    Add day configurations to existing Salesforce SLA workflows that are missing them.

    This fixes workflows that were created but failed to get day configs due to
    the day_order NOT NULL constraint.
    """
    import os
    from sqlalchemy import text
    from datetime import timezone

    expected_key = os.getenv("ADMIN_API_KEY", "")
    if admin_key != expected_key:
        raise HTTPException(status_code=403, detail="Invalid admin key")

    now = datetime.now(timezone.utc)

    # Day configs for each workflow
    WORKFLOW_DAYS = {
        "closing": [
            {"day_value": -14, "day_label": "14 Days to Closing", "phone_enabled": True, "email_enabled": True, "text_enabled": False, "task_description": "Review file for closing readiness."},
            {"day_value": -7, "day_label": "7 Days to Closing", "phone_enabled": True, "email_enabled": True, "text_enabled": True, "task_description": "Confirm borrower has scheduled closing."},
            {"day_value": -3, "day_label": "3 Days to Closing", "phone_enabled": True, "email_enabled": True, "text_enabled": True, "task_description": "Final closing confirmation."},
            {"day_value": -1, "day_label": "1 Day to Closing", "phone_enabled": True, "email_enabled": False, "text_enabled": True, "task_description": "Day before closing confirmation."},
            {"day_value": 0, "day_label": "Closing Day", "phone_enabled": True, "email_enabled": True, "text_enabled": False, "task_description": "Congratulate borrower."}
        ],
        "rate_lock": [
            {"day_value": 0, "day_label": "Rate Lock Confirmation", "phone_enabled": False, "email_enabled": True, "text_enabled": False, "task_description": "Send rate lock confirmation."},
            {"day_value": 1, "day_label": "Rate Lock Follow-up", "phone_enabled": True, "email_enabled": False, "text_enabled": False, "task_description": "Confirm borrower received lock confirmation."}
        ],
        "lock_expiration": [
            {"day_value": -7, "day_label": "7 Days to Lock Expiration", "phone_enabled": True, "email_enabled": True, "text_enabled": False, "task_description": "ALERT: Lock expires in 7 days."},
            {"day_value": -3, "day_label": "3 Days to Lock Expiration", "phone_enabled": True, "email_enabled": True, "text_enabled": True, "task_description": "URGENT: Lock expires in 3 days."},
            {"day_value": -1, "day_label": "1 Day to Lock Expiration", "phone_enabled": True, "email_enabled": True, "text_enabled": True, "task_description": "CRITICAL: Lock expires tomorrow."}
        ],
        "disclosure_sent": [
            {"day_value": 1, "day_label": "Disclosure Follow-up", "phone_enabled": True, "email_enabled": True, "text_enabled": False, "task_description": "Follow up on disclosure receipt."},
            {"day_value": 3, "day_label": "Disclosure Reminder", "phone_enabled": True, "email_enabled": True, "text_enabled": True, "task_description": "Reminder to sign disclosure."}
        ]
    }

    results = {"fixed": [], "skipped": [], "errors": []}

    for workflow_key, days in WORKFLOW_DAYS.items():
        try:
            # Get workflow ID
            workflow = db.execute(text("""
                SELECT id FROM workflow_configurations
                WHERE workflow_key = :key
            """), {"key": workflow_key}).fetchone()

            if not workflow:
                results["skipped"].append({"workflow_key": workflow_key, "reason": "workflow not found"})
                continue

            workflow_id = workflow[0]

            # Check if day configs already exist
            existing_days = db.execute(text("""
                SELECT COUNT(*) FROM workflow_day_configs
                WHERE workflow_id = :workflow_id
            """), {"workflow_id": workflow_id}).fetchone()[0]

            if existing_days > 0:
                results["skipped"].append({"workflow_key": workflow_key, "reason": f"already has {existing_days} day configs"})
                continue

            # Create day configurations
            for day_idx, day_config in enumerate(days, start=1):
                db.execute(text("""
                    INSERT INTO workflow_day_configs (
                        workflow_id, day_value, day_label, day_order,
                        phone_enabled, email_enabled, text_enabled,
                        task_description, is_active,
                        created_at, updated_at
                    ) VALUES (
                        :workflow_id, :day_value, :day_label, :day_order,
                        :phone_enabled, :email_enabled, :text_enabled,
                        :task_description, true,
                        :now, :now
                    )
                """), {
                    "workflow_id": workflow_id,
                    "day_value": day_config["day_value"],
                    "day_label": day_config["day_label"],
                    "day_order": day_idx,
                    "phone_enabled": day_config.get("phone_enabled", False),
                    "email_enabled": day_config.get("email_enabled", True),
                    "text_enabled": day_config.get("text_enabled", False),
                    "task_description": day_config.get("task_description", ""),
                    "now": now
                })

            results["fixed"].append({
                "workflow_key": workflow_key,
                "workflow_id": workflow_id,
                "days_created": len(days)
            })

        except Exception as e:
            results["errors"].append({"workflow_key": workflow_key, "error": "Internal server error"})

    db.commit()

    return {
        "success": len(results["errors"]) == 0,
        "message": f"Fixed {len(results['fixed'])} workflows, skipped {len(results['skipped'])}",
        "results": results
    }