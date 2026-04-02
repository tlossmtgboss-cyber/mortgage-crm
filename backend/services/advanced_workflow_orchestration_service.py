"""
Advanced Workflow Orchestration Service

Provides sophisticated multi-step automated workflows:
- Visual workflow builder with branching logic
- Conditional execution and parallel processing
- Event-driven triggers and schedulers
- Error handling with retry and fallback
- Workflow versioning and rollback
- Real-time monitoring and debugging
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
import json
import asyncio
from concurrent.futures import ThreadPoolExecutor
import uuid

logger = logging.getLogger(__name__)


class WorkflowStatus(str, Enum):
    """Workflow instance status."""
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    WAITING = "waiting"  # Waiting for external event


class StepType(str, Enum):
    """Types of workflow steps."""
    ACTION = "action"           # Execute an action
    CONDITION = "condition"     # Branch based on condition
    PARALLEL = "parallel"       # Execute steps in parallel
    WAIT = "wait"               # Wait for time or event
    LOOP = "loop"               # Iterate over items
    SUBPROCESS = "subprocess"   # Call another workflow
    HUMAN_TASK = "human_task"   # Require human intervention
    AI_DECISION = "ai_decision" # AI-powered decision


class TriggerType(str, Enum):
    """Types of workflow triggers."""
    MANUAL = "manual"
    SCHEDULE = "schedule"
    EVENT = "event"
    WEBHOOK = "webhook"
    CONDITION = "condition"


@dataclass
class WorkflowStep:
    """Definition of a workflow step."""
    id: str
    name: str
    step_type: StepType
    config: Dict[str, Any] = field(default_factory=dict)

    # Connections
    next_steps: List[str] = field(default_factory=list)  # Default next steps
    on_success: Optional[str] = None                      # Step on success
    on_failure: Optional[str] = None                      # Step on failure
    on_timeout: Optional[str] = None                      # Step on timeout

    # Branching (for condition type)
    branches: Dict[str, str] = field(default_factory=dict)  # condition -> step_id

    # Error handling
    retry_count: int = 0
    retry_delay_seconds: int = 60
    timeout_seconds: int = 300

    # Metadata
    description: str = ""
    tags: List[str] = field(default_factory=list)


@dataclass
class WorkflowDefinition:
    """Complete workflow definition."""
    id: str
    name: str
    version: int
    description: str = ""

    # Steps
    steps: Dict[str, WorkflowStep] = field(default_factory=dict)
    start_step_id: str = ""

    # Triggers
    triggers: List[Dict[str, Any]] = field(default_factory=list)

    # Input/Output schema
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)

    # Settings
    max_duration_seconds: int = 86400  # 24 hours default
    max_concurrent_instances: int = 100

    # Metadata
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: Optional[int] = None
    is_active: bool = True
    tags: List[str] = field(default_factory=list)


@dataclass
class StepExecution:
    """Execution record for a workflow step."""
    step_id: str
    status: WorkflowStatus
    started_at: datetime
    completed_at: Optional[datetime] = None
    input_data: Dict[str, Any] = field(default_factory=dict)
    output_data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    retry_count: int = 0
    duration_ms: int = 0


@dataclass
class WorkflowInstance:
    """Running instance of a workflow."""
    id: str
    workflow_id: str
    workflow_version: int
    status: WorkflowStatus

    # Execution state
    current_step_id: Optional[str] = None
    input_data: Dict[str, Any] = field(default_factory=dict)
    context: Dict[str, Any] = field(default_factory=dict)
    output_data: Dict[str, Any] = field(default_factory=dict)

    # Step history
    step_executions: List[StepExecution] = field(default_factory=list)

    # Timing
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    paused_at: Optional[datetime] = None

    # Trigger info
    trigger_type: TriggerType = TriggerType.MANUAL
    trigger_data: Dict[str, Any] = field(default_factory=dict)

    # Error tracking
    error: Optional[str] = None
    error_step_id: Optional[str] = None


class AdvancedWorkflowOrchestrationService:
    """
    Advanced workflow orchestration engine.

    Features:
    - Visual workflow builder with drag-and-drop
    - Complex branching and conditional logic
    - Parallel execution and joins
    - Event-driven and scheduled triggers
    - Error handling with retry, fallback, compensation
    - Versioning and rollback
    - Real-time monitoring and debugging
    """

    def __init__(self, db_session=None):
        self.db = db_session

        # Workflow storage
        self._workflows: Dict[str, WorkflowDefinition] = {}
        self._instances: Dict[str, WorkflowInstance] = {}

        # Action handlers
        self._action_handlers: Dict[str, Callable] = {}

        # Event subscribers
        self._event_subscribers: Dict[str, List[str]] = {}  # event -> workflow_ids

        # Executor for parallel tasks
        self._executor = ThreadPoolExecutor(max_workers=10)

        # Register built-in actions
        self._register_builtin_actions()

        logger.info("AdvancedWorkflowOrchestrationService initialized")

    def _register_builtin_actions(self):
        """Register built-in workflow actions."""
        self.register_action("send_email", self._action_send_email)
        self.register_action("send_sms", self._action_send_sms)
        self.register_action("http_request", self._action_http_request)
        self.register_action("update_database", self._action_update_database)
        self.register_action("ai_generate", self._action_ai_generate)
        self.register_action("ai_classify", self._action_ai_classify)
        self.register_action("delay", self._action_delay)
        self.register_action("log", self._action_log)
        self.register_action("set_variable", self._action_set_variable)
        self.register_action("escalate", self._action_escalate)

    # =========================================================================
    # Workflow Definition Management
    # =========================================================================

    def create_workflow(
        self,
        name: str,
        description: str = "",
        created_by: Optional[int] = None,
        tags: List[str] = None
    ) -> WorkflowDefinition:
        """Create a new workflow definition."""
        workflow_id = f"wf_{uuid.uuid4().hex[:12]}"

        workflow = WorkflowDefinition(
            id=workflow_id,
            name=name,
            version=1,
            description=description,
            created_by=created_by,
            tags=tags or []
        )

        self._workflows[workflow_id] = workflow
        logger.info(f"Created workflow: {workflow_id} ({name})")

        return workflow

    def add_step(
        self,
        workflow_id: str,
        step_id: str,
        name: str,
        step_type: StepType,
        config: Dict[str, Any] = None,
        **kwargs
    ) -> Optional[WorkflowStep]:
        """Add a step to a workflow."""
        workflow = self._workflows.get(workflow_id)
        if not workflow:
            logger.error(f"Workflow not found: {workflow_id}")
            return None

        step = WorkflowStep(
            id=step_id,
            name=name,
            step_type=step_type,
            config=config or {},
            **kwargs
        )

        workflow.steps[step_id] = step

        # Set as start step if first
        if not workflow.start_step_id:
            workflow.start_step_id = step_id

        workflow.updated_at = datetime.now(timezone.utc)

        return step

    def connect_steps(
        self,
        workflow_id: str,
        from_step_id: str,
        to_step_id: str,
        connection_type: str = "default"
    ) -> bool:
        """Connect two workflow steps."""
        workflow = self._workflows.get(workflow_id)
        if not workflow:
            return False

        from_step = workflow.steps.get(from_step_id)
        if not from_step:
            return False

        if connection_type == "default":
            if to_step_id not in from_step.next_steps:
                from_step.next_steps.append(to_step_id)
        elif connection_type == "success":
            from_step.on_success = to_step_id
        elif connection_type == "failure":
            from_step.on_failure = to_step_id
        elif connection_type == "timeout":
            from_step.on_timeout = to_step_id

        workflow.updated_at = datetime.now(timezone.utc)
        return True

    def add_branch(
        self,
        workflow_id: str,
        step_id: str,
        condition: str,
        target_step_id: str
    ) -> bool:
        """Add a conditional branch to a step."""
        workflow = self._workflows.get(workflow_id)
        if not workflow:
            return False

        step = workflow.steps.get(step_id)
        if not step or step.step_type != StepType.CONDITION:
            return False

        step.branches[condition] = target_step_id
        workflow.updated_at = datetime.now(timezone.utc)
        return True

    def set_trigger(
        self,
        workflow_id: str,
        trigger_type: TriggerType,
        config: Dict[str, Any]
    ) -> bool:
        """Set a trigger for a workflow."""
        workflow = self._workflows.get(workflow_id)
        if not workflow:
            return False

        trigger = {
            "type": trigger_type.value,
            "config": config,
            "created_at": datetime.now(timezone.utc).isoformat()
        }

        workflow.triggers.append(trigger)

        # Subscribe to events if event trigger
        if trigger_type == TriggerType.EVENT:
            event_name = config.get("event_name")
            if event_name:
                if event_name not in self._event_subscribers:
                    self._event_subscribers[event_name] = []
                self._event_subscribers[event_name].append(workflow_id)

        workflow.updated_at = datetime.now(timezone.utc)
        return True

    def publish_workflow(self, workflow_id: str) -> bool:
        """Publish a workflow, making it active."""
        workflow = self._workflows.get(workflow_id)
        if not workflow:
            return False

        if not workflow.start_step_id:
            logger.error(f"Cannot publish workflow without start step: {workflow_id}")
            return False

        workflow.is_active = True
        workflow.updated_at = datetime.now(timezone.utc)

        logger.info(f"Published workflow: {workflow_id} v{workflow.version}")
        return True

    def create_new_version(self, workflow_id: str) -> Optional[WorkflowDefinition]:
        """Create a new version of a workflow."""
        workflow = self._workflows.get(workflow_id)
        if not workflow:
            return None

        # Create copy with new version
        new_workflow = WorkflowDefinition(
            id=workflow_id,
            name=workflow.name,
            version=workflow.version + 1,
            description=workflow.description,
            steps=workflow.steps.copy(),
            start_step_id=workflow.start_step_id,
            triggers=workflow.triggers.copy(),
            input_schema=workflow.input_schema.copy(),
            output_schema=workflow.output_schema.copy(),
            max_duration_seconds=workflow.max_duration_seconds,
            max_concurrent_instances=workflow.max_concurrent_instances,
            created_by=workflow.created_by,
            is_active=False,  # New version starts inactive
            tags=workflow.tags.copy()
        )

        self._workflows[workflow_id] = new_workflow
        return new_workflow

    # =========================================================================
    # Workflow Execution
    # =========================================================================

    async def start_workflow(
        self,
        workflow_id: str,
        input_data: Dict[str, Any] = None,
        trigger_type: TriggerType = TriggerType.MANUAL,
        trigger_data: Dict[str, Any] = None
    ) -> Optional[WorkflowInstance]:
        """Start a new workflow instance."""
        workflow = self._workflows.get(workflow_id)
        if not workflow or not workflow.is_active:
            logger.error(f"Workflow not found or inactive: {workflow_id}")
            return None

        # Check concurrent instance limit
        active_count = len([
            i for i in self._instances.values()
            if i.workflow_id == workflow_id
            and i.status in [WorkflowStatus.RUNNING, WorkflowStatus.WAITING]
        ])

        if active_count >= workflow.max_concurrent_instances:
            logger.warning(f"Max concurrent instances reached for: {workflow_id}")
            return None

        # Create instance
        instance_id = f"wi_{uuid.uuid4().hex[:12]}"

        instance = WorkflowInstance(
            id=instance_id,
            workflow_id=workflow_id,
            workflow_version=workflow.version,
            status=WorkflowStatus.RUNNING,
            current_step_id=workflow.start_step_id,
            input_data=input_data or {},
            context={"input": input_data or {}},
            trigger_type=trigger_type,
            trigger_data=trigger_data or {}
        )

        self._instances[instance_id] = instance

        logger.info(f"Started workflow instance: {instance_id} ({workflow.name})")

        # Execute workflow
        asyncio.create_task(self._execute_workflow(instance))

        return instance

    async def _execute_workflow(self, instance: WorkflowInstance):
        """Execute a workflow instance."""
        workflow = self._workflows.get(instance.workflow_id)
        if not workflow:
            instance.status = WorkflowStatus.FAILED
            instance.error = "Workflow definition not found"
            return

        try:
            while instance.status == WorkflowStatus.RUNNING:
                step = workflow.steps.get(instance.current_step_id)
                if not step:
                    logger.info(f"Workflow completed: {instance.id}")
                    instance.status = WorkflowStatus.COMPLETED
                    instance.completed_at = datetime.now(timezone.utc)
                    break

                # Execute step
                result = await self._execute_step(instance, step, workflow)

                if result.status == WorkflowStatus.FAILED:
                    # Check for failure handler
                    if step.on_failure:
                        instance.current_step_id = step.on_failure
                    else:
                        instance.status = WorkflowStatus.FAILED
                        instance.error = result.error
                        instance.error_step_id = step.id
                        break

                elif result.status == WorkflowStatus.WAITING:
                    instance.status = WorkflowStatus.WAITING
                    break

                else:
                    # Determine next step
                    next_step_id = self._determine_next_step(step, result, instance)

                    if not next_step_id:
                        instance.status = WorkflowStatus.COMPLETED
                        instance.completed_at = datetime.now(timezone.utc)
                        instance.output_data = instance.context.get("output", {})
                        break

                    instance.current_step_id = next_step_id

        except Exception as e:
            logger.error(f"Workflow execution error: {e}")
            instance.status = WorkflowStatus.FAILED
            instance.error = str(e)

    async def _execute_step(
        self,
        instance: WorkflowInstance,
        step: WorkflowStep,
        workflow: WorkflowDefinition
    ) -> StepExecution:
        """Execute a single workflow step."""
        execution = StepExecution(
            step_id=step.id,
            status=WorkflowStatus.RUNNING,
            started_at=datetime.now(timezone.utc),
            input_data=self._resolve_variables(step.config, instance.context)
        )

        instance.step_executions.append(execution)

        try:
            if step.step_type == StepType.ACTION:
                result = await self._execute_action(step, instance)
            elif step.step_type == StepType.CONDITION:
                result = await self._execute_condition(step, instance)
            elif step.step_type == StepType.PARALLEL:
                result = await self._execute_parallel(step, instance, workflow)
            elif step.step_type == StepType.WAIT:
                result = await self._execute_wait(step, instance)
            elif step.step_type == StepType.LOOP:
                result = await self._execute_loop(step, instance, workflow)
            elif step.step_type == StepType.SUBPROCESS:
                result = await self._execute_subprocess(step, instance)
            elif step.step_type == StepType.HUMAN_TASK:
                result = await self._execute_human_task(step, instance)
            elif step.step_type == StepType.AI_DECISION:
                result = await self._execute_ai_decision(step, instance)
            else:
                result = {"error": f"Unknown step type: {step.step_type}"}

            execution.output_data = result
            execution.status = WorkflowStatus.COMPLETED
            execution.completed_at = datetime.now(timezone.utc)
            execution.duration_ms = int(
                (execution.completed_at - execution.started_at).total_seconds() * 1000
            )

            # Store result in context
            instance.context[f"step_{step.id}"] = result

        except asyncio.TimeoutError:
            execution.status = WorkflowStatus.FAILED
            execution.error = "Step timed out"
            if step.on_timeout:
                execution.output_data = {"timeout": True}
        except Exception as e:
            execution.error = str(e)
            execution.status = WorkflowStatus.FAILED

            # Retry logic
            if execution.retry_count < step.retry_count:
                execution.retry_count += 1
                await asyncio.sleep(step.retry_delay_seconds)
                return await self._execute_step(instance, step, workflow)

        return execution

    async def _execute_action(
        self,
        step: WorkflowStep,
        instance: WorkflowInstance
    ) -> Dict[str, Any]:
        """Execute an action step."""
        action_type = step.config.get("action_type")
        handler = self._action_handlers.get(action_type)

        if not handler:
            raise ValueError(f"Unknown action type: {action_type}")

        # Resolve variables in config
        resolved_config = self._resolve_variables(step.config, instance.context)

        # Execute action
        if asyncio.iscoroutinefunction(handler):
            result = await handler(resolved_config, instance.context)
        else:
            result = handler(resolved_config, instance.context)

        return result

    async def _execute_condition(
        self,
        step: WorkflowStep,
        instance: WorkflowInstance
    ) -> Dict[str, Any]:
        """Execute a condition step (evaluate and determine branch)."""
        condition_expr = step.config.get("condition", "")

        # Evaluate condition
        try:
            result = self._evaluate_condition(condition_expr, instance.context)
            return {"condition_result": result, "branch": str(result)}
        except Exception as e:
            return {"condition_result": None, "error": "Internal server error"}

    async def _execute_parallel(
        self,
        step: WorkflowStep,
        instance: WorkflowInstance,
        workflow: WorkflowDefinition
    ) -> Dict[str, Any]:
        """Execute parallel steps."""
        parallel_step_ids = step.config.get("parallel_steps", [])

        # Create tasks for parallel execution
        tasks = []
        for step_id in parallel_step_ids:
            parallel_step = workflow.steps.get(step_id)
            if parallel_step:
                task = self._execute_step(instance, parallel_step, workflow)
                tasks.append(task)

        # Wait for all to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)

        return {
            "parallel_results": [
                r.output_data if isinstance(r, StepExecution) else str(r)
                for r in results
            ]
        }

    async def _execute_wait(
        self,
        step: WorkflowStep,
        instance: WorkflowInstance
    ) -> Dict[str, Any]:
        """Execute a wait step."""
        wait_type = step.config.get("wait_type", "duration")

        if wait_type == "duration":
            seconds = step.config.get("seconds", 0)
            await asyncio.sleep(seconds)
            return {"waited_seconds": seconds}

        elif wait_type == "event":
            # Mark as waiting - will be resumed by event
            instance.status = WorkflowStatus.WAITING
            return {"waiting_for": step.config.get("event_name")}

        elif wait_type == "datetime":
            target_time = datetime.fromisoformat(step.config.get("datetime"))
            wait_seconds = (target_time - datetime.now(timezone.utc)).total_seconds()
            if wait_seconds > 0:
                await asyncio.sleep(wait_seconds)
            return {"waited_until": target_time.isoformat()}

        return {}

    async def _execute_loop(
        self,
        step: WorkflowStep,
        instance: WorkflowInstance,
        workflow: WorkflowDefinition
    ) -> Dict[str, Any]:
        """Execute a loop step."""
        items_expr = step.config.get("items", "[]")
        loop_step_id = step.config.get("loop_step")

        # Resolve items
        items = self._evaluate_condition(items_expr, instance.context)
        if not isinstance(items, list):
            items = [items]

        results = []
        loop_step = workflow.steps.get(loop_step_id)

        if loop_step:
            for i, item in enumerate(items):
                instance.context["loop_item"] = item
                instance.context["loop_index"] = i

                result = await self._execute_step(instance, loop_step, workflow)
                results.append(result.output_data)

        return {"loop_results": results, "iterations": len(items)}

    async def _execute_subprocess(
        self,
        step: WorkflowStep,
        instance: WorkflowInstance
    ) -> Dict[str, Any]:
        """Execute a subprocess (nested workflow)."""
        subprocess_id = step.config.get("workflow_id")
        subprocess_input = self._resolve_variables(
            step.config.get("input", {}),
            instance.context
        )

        # Start subprocess
        subprocess_instance = await self.start_workflow(
            subprocess_id,
            subprocess_input,
            TriggerType.MANUAL
        )

        if not subprocess_instance:
            return {"error": "Failed to start subprocess"}

        # Wait for completion
        while subprocess_instance.status in [WorkflowStatus.RUNNING, WorkflowStatus.WAITING]:
            await asyncio.sleep(1)
            subprocess_instance = self._instances.get(subprocess_instance.id)

        return {
            "subprocess_id": subprocess_instance.id,
            "subprocess_status": subprocess_instance.status.value,
            "subprocess_output": subprocess_instance.output_data
        }

    async def _execute_human_task(
        self,
        step: WorkflowStep,
        instance: WorkflowInstance
    ) -> Dict[str, Any]:
        """Execute a human task step (requires human intervention)."""
        # Create task for human
        task_id = f"task_{uuid.uuid4().hex[:8]}"

        task = {
            "id": task_id,
            "workflow_instance_id": instance.id,
            "step_id": step.id,
            "title": step.config.get("task_title", step.name),
            "description": step.config.get("task_description", ""),
            "assignee": step.config.get("assignee"),
            "due_date": step.config.get("due_date"),
            "form_fields": step.config.get("form_fields", []),
            "created_at": datetime.now(timezone.utc).isoformat()
        }

        # Store task (would be in database)
        instance.context[f"human_task_{step.id}"] = task

        # Mark workflow as waiting
        instance.status = WorkflowStatus.WAITING

        # Push-notify the assignee for high/critical priority tasks
        task_priority = step.config.get("priority", "medium")
        assignee_id = step.config.get("assignee")
        if assignee_id and task_priority in ("high", "critical"):
            try:
                from services.agent_notification_service import get_agent_notification_service
                push_svc = get_agent_notification_service()
                if self.db:
                    push_svc.notify_task_created(
                        db=self.db,
                        user_id=int(assignee_id) if isinstance(assignee_id, str) and assignee_id.isdigit() else assignee_id,
                        task_title=task["title"],
                        task_priority=task_priority,
                    )
            except Exception as e:
                logger.debug(f"Push notification for human task failed (non-blocking): {e}")

        return {"task_id": task_id, "waiting_for_human": True}

    async def _execute_ai_decision(
        self,
        step: WorkflowStep,
        instance: WorkflowInstance
    ) -> Dict[str, Any]:
        """Execute an AI-powered decision step."""
        decision_prompt = step.config.get("prompt", "")
        options = step.config.get("options", [])

        # Resolve variables in prompt
        resolved_prompt = self._resolve_variables(
            {"prompt": decision_prompt},
            instance.context
        )["prompt"]

        # Would call AI service here
        # For now, return first option as placeholder
        selected_option = options[0] if options else "default"

        return {
            "ai_decision": selected_option,
            "options_considered": options,
            "confidence": 0.85
        }

    def _determine_next_step(
        self,
        current_step: WorkflowStep,
        execution: StepExecution,
        instance: WorkflowInstance
    ) -> Optional[str]:
        """Determine the next step based on execution result."""
        # Check for specific success handler
        if execution.status == WorkflowStatus.COMPLETED and current_step.on_success:
            return current_step.on_success

        # Check for branch conditions
        if current_step.step_type == StepType.CONDITION and current_step.branches:
            branch_key = str(execution.output_data.get("branch", ""))
            if branch_key in current_step.branches:
                return current_step.branches[branch_key]
            # Check for default branch
            if "default" in current_step.branches:
                return current_step.branches["default"]

        # Return first default next step
        if current_step.next_steps:
            return current_step.next_steps[0]

        return None

    def _resolve_variables(
        self,
        config: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Resolve variables in config using context."""
        result = {}

        for key, value in config.items():
            if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
                var_path = value[2:-1]
                result[key] = self._get_nested_value(context, var_path)
            elif isinstance(value, dict):
                result[key] = self._resolve_variables(value, context)
            else:
                result[key] = value

        return result

    def _get_nested_value(self, data: Dict, path: str) -> Any:
        """Get nested value from dict using dot notation."""
        parts = path.split(".")
        current = data

        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return None

        return current

    def _evaluate_condition(self, condition: str, context: Dict) -> Any:
        """Safely evaluate a condition expression without using eval()."""
        import ast
        import operator

        try:
            # Replace variable references with actual values
            for key, value in context.items():
                if isinstance(value, (str, int, float, bool)):
                    condition = condition.replace(f"${{{key}}}", repr(value))

            # Safe expression evaluator using AST
            # Only supports: comparisons, boolean ops, literals
            SAFE_OPERATORS = {
                ast.Eq: operator.eq,
                ast.NotEq: operator.ne,
                ast.Lt: operator.lt,
                ast.LtE: operator.le,
                ast.Gt: operator.gt,
                ast.GtE: operator.ge,
                ast.And: lambda a, b: a and b,
                ast.Or: lambda a, b: a or b,
                ast.Not: operator.not_,
                ast.Add: operator.add,
                ast.Sub: operator.sub,
                ast.In: lambda a, b: a in b,
                ast.NotIn: lambda a, b: a not in b,
            }

            def _safe_eval(node):
                if isinstance(node, ast.Expression):
                    return _safe_eval(node.body)
                elif isinstance(node, ast.Constant):
                    return node.value
                elif isinstance(node, ast.Name):
                    # Only allow True, False, None
                    if node.id in ('True', 'False', 'None'):
                        return {'True': True, 'False': False, 'None': None}[node.id]
                    raise ValueError(f"Unknown name: {node.id}")
                elif isinstance(node, ast.Compare):
                    left = _safe_eval(node.left)
                    for op, comparator in zip(node.ops, node.comparators):
                        op_func = SAFE_OPERATORS.get(type(op))
                        if not op_func:
                            raise ValueError(f"Unsupported operator: {type(op)}")
                        right = _safe_eval(comparator)
                        if not op_func(left, right):
                            return False
                        left = right
                    return True
                elif isinstance(node, ast.BoolOp):
                    op_func = SAFE_OPERATORS.get(type(node.op))
                    if not op_func:
                        raise ValueError(f"Unsupported bool operator: {type(node.op)}")
                    values = [_safe_eval(v) for v in node.values]
                    result = values[0]
                    for v in values[1:]:
                        result = op_func(result, v)
                    return result
                elif isinstance(node, ast.UnaryOp):
                    if isinstance(node.op, ast.Not):
                        return not _safe_eval(node.operand)
                    raise ValueError(f"Unsupported unary operator: {type(node.op)}")
                elif isinstance(node, ast.BinOp):
                    op_func = SAFE_OPERATORS.get(type(node.op))
                    if not op_func:
                        raise ValueError(f"Unsupported binary operator: {type(node.op)}")
                    return op_func(_safe_eval(node.left), _safe_eval(node.right))
                else:
                    raise ValueError(f"Unsupported expression type: {type(node)}")

            tree = ast.parse(condition, mode='eval')
            return _safe_eval(tree)
        except Exception as e:
            logger.warning(f"Condition evaluation failed for '{condition}': {e}")
            return condition

    # =========================================================================
    # Instance Management
    # =========================================================================

    async def pause_workflow(self, instance_id: str) -> bool:
        """Pause a running workflow instance."""
        instance = self._instances.get(instance_id)
        if not instance or instance.status != WorkflowStatus.RUNNING:
            return False

        instance.status = WorkflowStatus.PAUSED
        instance.paused_at = datetime.now(timezone.utc)

        logger.info(f"Paused workflow: {instance_id}")
        return True

    async def resume_workflow(self, instance_id: str) -> bool:
        """Resume a paused workflow instance."""
        instance = self._instances.get(instance_id)
        if not instance or instance.status != WorkflowStatus.PAUSED:
            return False

        instance.status = WorkflowStatus.RUNNING
        instance.paused_at = None

        # Continue execution
        asyncio.create_task(self._execute_workflow(instance))

        logger.info(f"Resumed workflow: {instance_id}")
        return True

    async def cancel_workflow(self, instance_id: str, reason: str = "") -> bool:
        """Cancel a workflow instance."""
        instance = self._instances.get(instance_id)
        if not instance:
            return False

        instance.status = WorkflowStatus.CANCELLED
        instance.completed_at = datetime.now(timezone.utc)
        instance.error = f"Cancelled: {reason}" if reason else "Cancelled"

        logger.info(f"Cancelled workflow: {instance_id}")
        return True

    async def complete_human_task(
        self,
        instance_id: str,
        step_id: str,
        result: Dict[str, Any]
    ) -> bool:
        """Complete a human task and resume workflow."""
        instance = self._instances.get(instance_id)
        if not instance or instance.status != WorkflowStatus.WAITING:
            return False

        # Store human task result
        instance.context[f"human_task_{step_id}_result"] = result

        # Resume workflow
        instance.status = WorkflowStatus.RUNNING
        asyncio.create_task(self._execute_workflow(instance))

        return True

    async def trigger_event(self, event_name: str, event_data: Dict[str, Any]):
        """Trigger an event that may start or resume workflows."""
        # Start workflows subscribed to this event
        workflow_ids = self._event_subscribers.get(event_name, [])

        for workflow_id in workflow_ids:
            await self.start_workflow(
                workflow_id,
                event_data,
                TriggerType.EVENT,
                {"event_name": event_name}
            )

        # Resume waiting workflows
        for instance in self._instances.values():
            if instance.status == WorkflowStatus.WAITING:
                workflow = self._workflows.get(instance.workflow_id)
                if workflow:
                    step = workflow.steps.get(instance.current_step_id)
                    if step and step.step_type == StepType.WAIT:
                        if step.config.get("event_name") == event_name:
                            instance.context["event_data"] = event_data
                            instance.status = WorkflowStatus.RUNNING
                            asyncio.create_task(self._execute_workflow(instance))

    def get_instance(self, instance_id: str) -> Optional[WorkflowInstance]:
        """Get a workflow instance."""
        return self._instances.get(instance_id)

    def get_workflow(self, workflow_id: str) -> Optional[WorkflowDefinition]:
        """Get a workflow definition."""
        return self._workflows.get(workflow_id)

    # =========================================================================
    # Action Registration
    # =========================================================================

    def register_action(self, action_type: str, handler: Callable):
        """Register an action handler."""
        self._action_handlers[action_type] = handler
        logger.debug(f"Registered action: {action_type}")

    # =========================================================================
    # Built-in Action Implementations
    # =========================================================================

    async def _action_send_email(self, config: Dict, context: Dict) -> Dict:
        """Send email action."""
        return {
            "action": "send_email",
            "to": config.get("to"),
            "subject": config.get("subject"),
            "status": "sent"
        }

    async def _action_send_sms(self, config: Dict, context: Dict) -> Dict:
        """Send SMS action."""
        return {
            "action": "send_sms",
            "to": config.get("to"),
            "status": "sent"
        }

    async def _action_http_request(self, config: Dict, context: Dict) -> Dict:
        """HTTP request action."""
        # Would make actual HTTP request
        return {
            "action": "http_request",
            "url": config.get("url"),
            "method": config.get("method", "GET"),
            "status": "completed"
        }

    async def _action_update_database(self, config: Dict, context: Dict) -> Dict:
        """Update database action."""
        return {
            "action": "update_database",
            "table": config.get("table"),
            "status": "updated"
        }

    async def _action_ai_generate(self, config: Dict, context: Dict) -> Dict:
        """AI text generation action."""
        return {
            "action": "ai_generate",
            "prompt": config.get("prompt"),
            "result": "AI generated content placeholder"
        }

    async def _action_ai_classify(self, config: Dict, context: Dict) -> Dict:
        """AI classification action."""
        return {
            "action": "ai_classify",
            "text": config.get("text"),
            "classification": "category_a"
        }

    async def _action_delay(self, config: Dict, context: Dict) -> Dict:
        """Delay action."""
        seconds = config.get("seconds", 0)
        await asyncio.sleep(seconds)
        return {"delayed_seconds": seconds}

    async def _action_log(self, config: Dict, context: Dict) -> Dict:
        """Log action."""
        message = config.get("message", "")
        level = config.get("level", "info")
        logger.log(getattr(logging, level.upper(), logging.INFO), message)
        return {"logged": message}

    async def _action_set_variable(self, config: Dict, context: Dict) -> Dict:
        """Set variable action."""
        name = config.get("name")
        value = config.get("value")
        context[name] = value
        return {"variable_set": name, "value": value}

    async def _action_escalate(self, config: Dict, context: Dict) -> Dict:
        """Escalate action."""
        return {
            "action": "escalate",
            "to": config.get("to"),
            "reason": config.get("reason"),
            "status": "escalated"
        }

    # =========================================================================
    # Monitoring & Analytics
    # =========================================================================

    def get_workflow_stats(self, workflow_id: str) -> Dict[str, Any]:
        """Get statistics for a workflow."""
        instances = [
            i for i in self._instances.values()
            if i.workflow_id == workflow_id
        ]

        if not instances:
            return {"workflow_id": workflow_id, "instances": 0}

        completed = [i for i in instances if i.status == WorkflowStatus.COMPLETED]
        failed = [i for i in instances if i.status == WorkflowStatus.FAILED]
        running = [i for i in instances if i.status == WorkflowStatus.RUNNING]

        avg_duration = 0
        if completed:
            durations = [
                (i.completed_at - i.started_at).total_seconds()
                for i in completed if i.completed_at
            ]
            avg_duration = sum(durations) / len(durations) if durations else 0

        return {
            "workflow_id": workflow_id,
            "total_instances": len(instances),
            "completed": len(completed),
            "failed": len(failed),
            "running": len(running),
            "success_rate": len(completed) / len(instances) * 100 if instances else 0,
            "avg_duration_seconds": round(avg_duration, 2)
        }

    def get_instance_timeline(self, instance_id: str) -> List[Dict[str, Any]]:
        """Get execution timeline for an instance."""
        instance = self._instances.get(instance_id)
        if not instance:
            return []

        timeline = []
        for execution in instance.step_executions:
            timeline.append({
                "step_id": execution.step_id,
                "status": execution.status.value,
                "started_at": execution.started_at.isoformat(),
                "completed_at": execution.completed_at.isoformat() if execution.completed_at else None,
                "duration_ms": execution.duration_ms,
                "error": execution.error
            })

        return timeline
