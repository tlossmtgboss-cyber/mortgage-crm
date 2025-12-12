"""
Workflow SLA System API Routes

API endpoints for the SLA-driven workflow task generation system.
Provides endpoints for:
- Workflow enrollment and management
- Task completion and tracking
- Role assignments
- Scheduled task execution
"""

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks, Request
from sqlalchemy.orm import Session
from typing import Optional, List, Callable, Any
from pydantic import BaseModel
from datetime import datetime

from services.workflow_sla_service import WorkflowSLAService, get_workflow_service
from services.workflow_task_generator import TaskGeneratorService, get_task_generator
from services.workflow_role_assignment import RoleAssignmentService, get_role_assignment_service
from services.workflow_scheduler import WorkflowScheduler, run_scheduled_workflow_tasks

import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/workflow-sla", tags=["Workflow SLA"])

# ============================================================================
# DEPENDENCY INJECTION STORAGE
# ============================================================================

_get_db: Callable = None
_get_current_user: Callable = None
_User: Any = None


def set_dependencies(get_db_func: Callable, get_current_user_func: Callable, user_model: Any):
    """Set dependencies from main.py to avoid circular imports."""
    global _get_db, _get_current_user, _User
    _get_db = get_db_func
    _get_current_user = get_current_user_func
    _User = user_model
    logger.info("Workflow SLA routes dependencies set")


def get_db():
    """Get database session dependency - wrapper for injected dependency."""
    if _get_db is None:
        raise RuntimeError("Workflow SLA routes not initialized. Call set_dependencies first.")
    yield from _get_db()


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
    status = service.get_workflow_status(instance_id)

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
    return {"workflows": service.get_active_workflows_for_lead(lead_id)}


@router.get("/loans/{loan_id}/workflows")
async def get_loan_workflows(
    loan_id: int,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all active workflows for a loan."""
    service = get_workflow_service(db)
    return {"workflows": service.get_active_workflows_for_loan(loan_id)}


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
        background_tasks.add_task(run_scheduled_workflow_tasks, db)
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

    integration = WorkflowDialerIntegration(db)
    # Base URL would come from config in production
    base_url = "https://api.example.com"

    result = integration.create_dialer_session_from_workflow(
        agent_id=current_user.id,
        workflow_task_ids=request.workflow_task_ids,
        base_url=base_url
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
    """
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
            result = db.execute(text(f"""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'tasks' AND column_name = '{col_name}'
            """))
            if not result.fetchone():
                db.execute(text(f"ALTER TABLE tasks ADD COLUMN {col_name} {col_type}"))
                db.commit()
                added.append(col_name)
                logger.info(f"✅ Added '{col_name}' column to tasks table")
            else:
                already_exists.append(col_name)
        except Exception as e:
            db.rollback()
            errors.append({"column": col_name, "error": str(e)})
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
        except Exception as e:
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
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Repair workflow tables by adding any missing columns.
    Safe to run multiple times - skips existing columns.
    """
    from sqlalchemy import text

    results = {
        "workflow_instances": [],
        "workflow_task_instances": [],
        "workflow_role_assignments": [],
        "errors": []
    }

    # Define expected columns for each table
    table_columns = {
        "workflow_instances": [
            ("organization_id", "INTEGER NOT NULL DEFAULT 1"),
            ("lead_id", "INTEGER"),
            ("loan_id", "INTEGER"),
            ("workflow_type", "VARCHAR(100) NOT NULL DEFAULT 'prospect'"),
            ("workflow_config_id", "INTEGER"),
            ("status", "VARCHAR(50) DEFAULT 'active'"),
            ("current_day", "INTEGER DEFAULT 1"),
            ("started_at", "TIMESTAMP WITH TIME ZONE DEFAULT NOW()"),
            ("paused_at", "TIMESTAMP WITH TIME ZONE"),
            ("completed_at", "TIMESTAMP WITH TIME ZONE"),
            ("cancelled_at", "TIMESTAMP WITH TIME ZONE"),
            ("next_check_at", "TIMESTAMP WITH TIME ZONE"),
            ("metadata", "JSONB DEFAULT '{}'"),
            ("created_at", "TIMESTAMP WITH TIME ZONE DEFAULT NOW()"),
            ("updated_at", "TIMESTAMP WITH TIME ZONE DEFAULT NOW()"),
        ],
        "workflow_task_instances": [
            ("workflow_instance_id", "INTEGER"),
            ("task_type", "VARCHAR(50) NOT NULL DEFAULT 'manual'"),
            ("task_name", "VARCHAR(255) NOT NULL DEFAULT 'Task'"),
            ("day_number", "INTEGER NOT NULL DEFAULT 1"),
            ("status", "VARCHAR(50) DEFAULT 'scheduled'"),
            ("route", "VARCHAR(50) DEFAULT 'task_list'"),
            ("assigned_user_id", "INTEGER"),
            ("lead_id", "INTEGER"),
            ("loan_id", "INTEGER"),
            ("due_date", "TIMESTAMP WITH TIME ZONE"),
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
                result = db.execute(text(f"""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name = '{table_name}' AND column_name = '{col_name}'
                """))
                if not result.fetchone():
                    # Add the column
                    db.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_def}"))
                    db.commit()
                    results[table_name].append({"column": col_name, "status": "added"})
                    logger.info(f"✅ Added column {col_name} to {table_name}")
                else:
                    results[table_name].append({"column": col_name, "status": "exists"})
            except Exception as e:
                db.rollback()
                results["errors"].append({"table": table_name, "column": col_name, "error": str(e)})
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
        except Exception as e:
            db.rollback()
            # Ignore index errors - not critical

    added_count = sum(len([c for c in cols if c.get("status") == "added"]) for cols in results.values() if isinstance(cols, list))

    return {
        "success": len(results["errors"]) == 0,
        "results": results,
        "summary": {
            "columns_added": added_count,
            "errors": len(results["errors"])
        }
    }
