"""
Perennia AI - Task Automation Tools
===================================
Tools for the Task Automation Agent handling workflow tasks and automation.
8 tools for task management, workflow automation, and productivity.
"""

from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from .base import (
    mortgage_tool,
    ToolResult,
    execute_query,
    execute_single,
    format_date,
)


# =============================================================================
# Task Automation Tools (8 tools)
# =============================================================================

@mortgage_tool(
    name="create_task",
    description="Create a new task with optional automation rules",
    agent_roles=["task_automation"],
    risk_level="LOW",
    parameters={
        "title": "Task title",
        "description": "Task description",
        "due_date": "Due date (YYYY-MM-DD)",
        "priority": "Priority: low, normal, high, urgent",
        "category": "Category: follow_up, document, call, review, compliance, other",
        "assigned_to": "User ID to assign to",
        "loan_id": "Optional loan ID to link",
        "lead_id": "Optional lead ID to link",
    },
)
def create_task(
    title: str,
    description: Optional[str] = None,
    due_date: Optional[str] = None,
    priority: str = "normal",
    category: str = "other",
    assigned_to: Optional[str] = None,
    loan_id: Optional[str] = None,
    lead_id: Optional[str] = None,
) -> ToolResult:
    """Create a new task."""
    # Default due date is 3 business days from now
    if not due_date:
        due = datetime.now() + timedelta(days=3)
        # Skip weekends
        while due.weekday() >= 5:
            due += timedelta(days=1)
        due_date = due.strftime("%Y-%m-%d")

    import uuid
    task_id = f"TSK-{str(uuid.uuid4())[:8].upper()}"

    # Get related entity info
    related_info = {}
    if loan_id:
        loan = execute_single(
            "SELECT loan_number, borrower_name FROM loans WHERE id = :id",
            {"id": loan_id}
        )
        if loan:
            related_info["loan"] = {
                "id": loan_id,
                "number": loan.get("loan_number"),
                "borrower": loan.get("borrower_name"),
            }

    if lead_id:
        lead = execute_single(
            "SELECT first_name, last_name FROM leads WHERE id = :id",
            {"id": lead_id}
        )
        if lead:
            related_info["lead"] = {
                "id": lead_id,
                "name": f"{lead.get('first_name', '')} {lead.get('last_name', '')}".strip(),
            }

    task = {
        "task_id": task_id,
        "title": title,
        "description": description,
        "due_date": due_date,
        "priority": priority,
        "category": category,
        "assigned_to": assigned_to,
        "loan_id": loan_id,
        "lead_id": lead_id,
        "status": "pending",
        "related": related_info,
        "created_at": datetime.now().isoformat(),
    }

    return ToolResult.success(
        data=task,
        message=f"Task created: {title} (due {due_date})",
    )


@mortgage_tool(
    name="get_task_queue",
    description="Get prioritized task queue for user or team",
    agent_roles=["task_automation"],
    risk_level="LOW",
    parameters={
        "user_id": "Optional user ID filter",
        "status": "Status filter: pending, in_progress, completed, overdue",
        "category": "Optional category filter",
        "priority": "Optional priority filter",
        "loan_id": "Optional loan ID filter",
        "lead_id": "Optional lead ID filter",
        "limit": "Maximum tasks to return",
    },
)
def get_task_queue(
    user_id: Optional[str] = None,
    status: Optional[str] = None,
    category: Optional[str] = None,
    priority: Optional[str] = None,
    loan_id: Optional[str] = None,
    lead_id: Optional[str] = None,
    limit: int = 50,
) -> ToolResult:
    """Get prioritized task queue."""
    params = {"limit": limit}
    filters = ["1=1"]

    if user_id:
        filters.append("t.assigned_to = :user_id")
        params["user_id"] = user_id

    if status:
        if status == "overdue":
            filters.append("t.due_date < CURRENT_DATE AND t.status NOT IN ('completed', 'cancelled')")
        else:
            filters.append("t.status = :status")
            params["status"] = status
    else:
        filters.append("t.status NOT IN ('completed', 'cancelled')")

    if category:
        filters.append("t.category = :category")
        params["category"] = category

    if priority:
        filters.append("t.priority = :priority")
        params["priority"] = priority

    if loan_id:
        filters.append("t.loan_id = :loan_id")
        params["loan_id"] = loan_id

    if lead_id:
        filters.append("t.lead_id = :lead_id")
        params["lead_id"] = lead_id

    where_sql = " AND ".join(filters)

    results = execute_query(f"""
        SELECT
            t.id, t.task_id, t.title, t.description, t.due_date,
            t.priority, t.status, t.category, t.assigned_to,
            t.loan_id, t.lead_id, t.created_at,
            l.first_name, l.last_name,
            ln.loan_number, ln.borrower_name,
            u.name as assigned_name
        FROM tasks t
        LEFT JOIN leads l ON t.lead_id = l.id::text
        LEFT JOIN loans ln ON t.loan_id = ln.id::text
        LEFT JOIN users u ON t.assigned_to = u.id::text
        WHERE {where_sql}
        ORDER BY
            CASE t.priority
                WHEN 'urgent' THEN 1
                WHEN 'high' THEN 2
                WHEN 'normal' THEN 3
                ELSE 4
            END,
            t.due_date ASC NULLS LAST
        LIMIT :limit
    """, params)

    tasks = []
    today = datetime.now().date()

    for r in results:
        due_date = r.get("due_date")
        is_overdue = False
        days_until_due = None

        if due_date:
            if hasattr(due_date, 'date'):
                due_date_obj = due_date.date()
            elif isinstance(due_date, str):
                due_date_obj = datetime.strptime(due_date, "%Y-%m-%d").date()
            else:
                due_date_obj = due_date

            is_overdue = due_date_obj < today and r.get("status") not in ("completed", "cancelled")
            days_until_due = (due_date_obj - today).days

        tasks.append({
            "id": r.get("id"),
            "task_id": r.get("task_id"),
            "title": r.get("title"),
            "description": r.get("description"),
            "due_date": format_date(r.get("due_date")),
            "days_until_due": days_until_due,
            "priority": r.get("priority"),
            "status": r.get("status"),
            "category": r.get("category"),
            "is_overdue": is_overdue,
            "assigned_to": r.get("assigned_to"),
            "assigned_name": r.get("assigned_name"),
            "lead": {
                "id": r.get("lead_id"),
                "name": f"{r.get('first_name', '')} {r.get('last_name', '')}".strip(),
            } if r.get("lead_id") else None,
            "loan": {
                "id": r.get("loan_id"),
                "number": r.get("loan_number"),
                "borrower": r.get("borrower_name"),
            } if r.get("loan_id") else None,
        })

    # Summary stats
    overdue_count = sum(1 for t in tasks if t["is_overdue"])
    urgent_count = sum(1 for t in tasks if t["priority"] == "urgent")
    due_today = sum(1 for t in tasks if t["days_until_due"] == 0)

    data = {
        "tasks": tasks,
        "total_count": len(tasks),
        "summary": {
            "overdue": overdue_count,
            "urgent": urgent_count,
            "due_today": due_today,
        },
        "filters_applied": {
            "user_id": user_id,
            "status": status,
            "category": category,
            "priority": priority,
        },
    }

    return ToolResult.success(
        data=data,
        message=f"Found {len(tasks)} tasks ({overdue_count} overdue, {urgent_count} urgent)",
    )


@mortgage_tool(
    name="update_task_status",
    description="Update task status and add notes",
    agent_roles=["task_automation"],
    risk_level="LOW",
    parameters={
        "task_id": "Task ID",
        "status": "New status: pending, in_progress, completed, cancelled",
        "notes": "Optional status update notes",
        "completion_details": "Optional completion details dict",
    },
)
def update_task_status(
    task_id: str,
    status: str,
    notes: Optional[str] = None,
    completion_details: Optional[Dict] = None,
) -> ToolResult:
    """Update task status."""
    # Get current task
    task = execute_single("""
        SELECT id, title, status as current_status, assigned_to
        FROM tasks
        WHERE id = :id OR task_id = :id
    """, {"id": task_id})

    if not task:
        return ToolResult.no_data(f"Task {task_id} not found")

    data = {
        "task_id": task_id,
        "title": task.get("title"),
        "previous_status": task.get("current_status"),
        "new_status": status,
        "notes": notes,
        "updated_at": datetime.now().isoformat(),
    }

    if status == "completed":
        data["completed_at"] = datetime.now().isoformat()
        data["completion_details"] = completion_details

    if status == "in_progress" and task.get("current_status") == "pending":
        data["started_at"] = datetime.now().isoformat()

    return ToolResult.success(
        data=data,
        message=f"Task status updated: {task.get('current_status')} → {status}",
    )


@mortgage_tool(
    name="assign_task",
    description="Assign or reassign a task to a user",
    agent_roles=["task_automation"],
    risk_level="LOW",
    parameters={
        "task_id": "Task ID to assign",
        "user_id": "User ID to assign to",
        "auto_assign": "Use auto-assignment based on workload",
        "notify": "Send notification to assignee",
    },
)
def assign_task(
    task_id: str,
    user_id: Optional[str] = None,
    auto_assign: bool = False,
    notify: bool = True,
) -> ToolResult:
    """Assign task to user."""
    # Get task details
    task = execute_single("""
        SELECT id, title, category, priority, assigned_to as current_assignee
        FROM tasks
        WHERE id = :id OR task_id = :id
    """, {"id": task_id})

    if not task:
        return ToolResult.no_data(f"Task {task_id} not found")

    assigned_user = user_id

    if auto_assign and not user_id:
        # Get team workloads for auto-assignment
        workloads = execute_query("""
            SELECT
                u.id, u.name,
                COUNT(t.id) as open_tasks,
                COUNT(CASE WHEN t.priority = 'urgent' THEN 1 END) as urgent_tasks
            FROM users u
            LEFT JOIN tasks t ON t.assigned_to = u.id::text
                AND t.status NOT IN ('completed', 'cancelled')
            WHERE u.role = 'loan_officer' AND u.status = 'active'
            GROUP BY u.id, u.name
            ORDER BY open_tasks ASC, urgent_tasks ASC
            LIMIT 5
        """)

        if workloads:
            # Assign to user with lowest workload
            assigned_user = str(workloads[0].get("id"))
            assignment_reason = "auto_assigned_lowest_workload"
        else:
            return ToolResult.error("No available users for auto-assignment")
    else:
        assignment_reason = "manual_assignment"

    # Get assignee info
    assignee = execute_single(
        "SELECT id, name, email FROM users WHERE id = :id",
        {"id": assigned_user}
    ) if assigned_user else None

    data = {
        "task_id": task_id,
        "title": task.get("title"),
        "previous_assignee": task.get("current_assignee"),
        "assigned_to": assigned_user,
        "assignee_name": assignee.get("name") if assignee else None,
        "assignment_reason": assignment_reason,
        "notification_sent": notify and assignee is not None,
        "assigned_at": datetime.now().isoformat(),
    }

    return ToolResult.success(
        data=data,
        message=f"Task assigned to {assignee.get('name') if assignee else 'user'}",
    )


@mortgage_tool(
    name="get_task_templates",
    description="Get available task templates for workflows",
    agent_roles=["task_automation"],
    risk_level="LOW",
    parameters={
        "template_type": "Filter by type: loan_stage, document, compliance, custom",
        "trigger_event": "Filter by trigger event",
        "include_inactive": "Include inactive templates",
    },
)
def get_task_templates(
    template_type: Optional[str] = None,
    trigger_event: Optional[str] = None,
    include_inactive: bool = False,
) -> ToolResult:
    """Get task templates."""
    params = {}
    filters = ["1=1"]

    if template_type:
        filters.append("tt.template_type = :template_type")
        params["template_type"] = template_type

    if trigger_event:
        filters.append("tt.trigger_event = :trigger_event")
        params["trigger_event"] = trigger_event

    if not include_inactive:
        filters.append("tt.is_active = true")

    where_sql = " AND ".join(filters)

    templates = execute_query(f"""
        SELECT
            tt.id, tt.template_id, tt.name, tt.description,
            tt.template_type, tt.trigger_event, tt.is_active,
            tt.task_count, tt.created_at
        FROM task_templates tt
        WHERE {where_sql}
        ORDER BY tt.name
    """, params)

    # If no templates in DB, return default templates
    if not templates:
        templates = [
            {
                "template_id": "TPL-NEWLOAN",
                "name": "New Loan Application",
                "description": "Tasks for new loan applications",
                "template_type": "loan_stage",
                "trigger_event": "loan_created",
                "task_count": 5,
                "is_active": True,
            },
            {
                "template_id": "TPL-DOCREQ",
                "name": "Document Request Follow-up",
                "description": "Follow-up tasks for document requests",
                "template_type": "document",
                "trigger_event": "document_requested",
                "task_count": 3,
                "is_active": True,
            },
            {
                "template_id": "TPL-CLOSING",
                "name": "Closing Checklist",
                "description": "Tasks for closing preparation",
                "template_type": "loan_stage",
                "trigger_event": "clear_to_close",
                "task_count": 8,
                "is_active": True,
            },
            {
                "template_id": "TPL-COMPLIANCE",
                "name": "Compliance Review",
                "description": "Compliance checklist tasks",
                "template_type": "compliance",
                "trigger_event": "submission",
                "task_count": 6,
                "is_active": True,
            },
        ]

    template_list = []
    for t in templates:
        template_list.append({
            "template_id": t.get("template_id") or t.get("id"),
            "name": t.get("name"),
            "description": t.get("description"),
            "type": t.get("template_type"),
            "trigger_event": t.get("trigger_event"),
            "task_count": t.get("task_count", 0),
            "is_active": t.get("is_active", True),
        })

    data = {
        "templates": template_list,
        "total_count": len(template_list),
        "filters_applied": {
            "template_type": template_type,
            "trigger_event": trigger_event,
        },
    }

    return ToolResult.success(
        data=data,
        message=f"Found {len(template_list)} task templates",
    )


@mortgage_tool(
    name="execute_workflow",
    description="Execute a workflow template to create tasks",
    agent_roles=["task_automation"],
    risk_level="MEDIUM",
    parameters={
        "template_id": "Template ID to execute",
        "loan_id": "Loan ID to link tasks",
        "lead_id": "Lead ID to link tasks",
        "assigned_to": "User ID to assign tasks",
        "start_date": "Start date for task sequence",
        "context": "Additional context for task customization",
    },
)
def execute_workflow(
    template_id: str,
    loan_id: Optional[str] = None,
    lead_id: Optional[str] = None,
    assigned_to: Optional[str] = None,
    start_date: Optional[str] = None,
    context: Optional[Dict] = None,
) -> ToolResult:
    """Execute workflow template."""
    if not start_date:
        start_date = datetime.now().strftime("%Y-%m-%d")

    base_date = datetime.strptime(start_date, "%Y-%m-%d")

    # Get template details
    template = execute_single("""
        SELECT id, name, task_count FROM task_templates
        WHERE id = :id OR template_id = :id
    """, {"id": template_id})

    # Get template tasks
    template_tasks = execute_query("""
        SELECT title, description, category, priority, due_days_offset, sequence
        FROM task_template_items
        WHERE template_id = :template_id
        ORDER BY sequence
    """, {"template_id": template_id})

    # Generate execution ID
    import uuid
    execution_id = f"WF-{str(uuid.uuid4())[:8].upper()}"

    # Create tasks from template
    tasks_created = []
    for i, task_def in enumerate(template_tasks or []):
        due_offset = task_def.get("due_days_offset", 3)
        task_due = base_date + timedelta(days=due_offset)

        # Skip weekends
        while task_due.weekday() >= 5:
            task_due += timedelta(days=1)

        task_id = f"TSK-{str(uuid.uuid4())[:8].upper()}"

        tasks_created.append({
            "task_id": task_id,
            "sequence": i + 1,
            "title": task_def.get("title"),
            "description": task_def.get("description"),
            "category": task_def.get("category", "other"),
            "priority": task_def.get("priority", "normal"),
            "due_date": task_due.strftime("%Y-%m-%d"),
            "assigned_to": assigned_to,
            "loan_id": loan_id,
            "lead_id": lead_id,
            "status": "pending",
        })

    data = {
        "execution_id": execution_id,
        "template_id": template_id,
        "template_name": template.get("name") if template else None,
        "loan_id": loan_id,
        "lead_id": lead_id,
        "assigned_to": assigned_to,
        "start_date": start_date,
        "tasks_created": tasks_created,
        "task_count": len(tasks_created),
        "executed_at": datetime.now().isoformat(),
        "status": "completed",
    }

    return ToolResult.success(
        data=data,
        message=f"Workflow executed: {len(tasks_created)} tasks created",
    )


@mortgage_tool(
    name="get_workflow_status",
    description="Get status of an executed workflow",
    agent_roles=["task_automation"],
    risk_level="LOW",
    parameters={
        "execution_id": "Workflow execution ID",
        "loan_id": "Or get workflow status by loan ID",
        "include_task_details": "Include individual task details",
    },
)
def get_workflow_status(
    execution_id: Optional[str] = None,
    loan_id: Optional[str] = None,
    include_task_details: bool = True,
) -> ToolResult:
    """Get workflow execution status."""
    if execution_id:
        # Get by execution ID
        workflow = execute_single("""
            SELECT we.*, tt.name as template_name
            FROM workflow_executions we
            LEFT JOIN task_templates tt ON we.template_id = tt.id
            WHERE we.execution_id = :execution_id
        """, {"execution_id": execution_id})

        if not workflow:
            return ToolResult.no_data(f"Workflow {execution_id} not found")

        params = {"execution_id": execution_id}
        task_filter = "workflow_execution_id = :execution_id"
    elif loan_id:
        # Get workflows for loan
        params = {"loan_id": loan_id}
        task_filter = "loan_id = :loan_id"
        workflow = {"loan_id": loan_id}
    else:
        return ToolResult.error("Either execution_id or loan_id required")

    # Get task status summary
    task_summary = execute_single(f"""
        SELECT
            COUNT(*) as total,
            COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed,
            COUNT(CASE WHEN status = 'in_progress' THEN 1 END) as in_progress,
            COUNT(CASE WHEN status = 'pending' THEN 1 END) as pending,
            COUNT(CASE WHEN due_date < CURRENT_DATE AND status NOT IN ('completed', 'cancelled') THEN 1 END) as overdue
        FROM tasks
        WHERE {task_filter}
    """, params)

    # Get individual tasks if requested
    tasks = []
    if include_task_details:
        task_results = execute_query(f"""
            SELECT
                t.id, t.task_id, t.title, t.status, t.priority,
                t.due_date, t.completed_at
            FROM tasks t
            WHERE {task_filter}
            ORDER BY t.due_date, t.id
        """, params)

        for t in task_results:
            tasks.append({
                "task_id": t.get("task_id"),
                "title": t.get("title"),
                "status": t.get("status"),
                "priority": t.get("priority"),
                "due_date": format_date(t.get("due_date")),
                "completed_at": format_date(t.get("completed_at")),
            })

    total = task_summary.get("total", 0) if task_summary else 0
    completed = task_summary.get("completed", 0) if task_summary else 0
    progress_pct = round((completed / total) * 100, 1) if total > 0 else 0

    # Determine overall status
    if completed == total and total > 0:
        overall_status = "completed"
    elif task_summary and task_summary.get("overdue", 0) > 0:
        overall_status = "at_risk"
    elif task_summary and task_summary.get("in_progress", 0) > 0:
        overall_status = "in_progress"
    else:
        overall_status = "pending"

    data = {
        "execution_id": execution_id,
        "loan_id": loan_id,
        "template_name": workflow.get("template_name") if workflow else None,
        "overall_status": overall_status,
        "progress": {
            "total": total,
            "completed": completed,
            "in_progress": task_summary.get("in_progress", 0) if task_summary else 0,
            "pending": task_summary.get("pending", 0) if task_summary else 0,
            "overdue": task_summary.get("overdue", 0) if task_summary else 0,
            "percent_complete": progress_pct,
        },
        "tasks": tasks if include_task_details else None,
    }

    return ToolResult.success(
        data=data,
        message=f"Workflow {progress_pct}% complete ({completed}/{total} tasks)",
    )


@mortgage_tool(
    name="bulk_update_tasks",
    description="Perform bulk updates on multiple tasks",
    agent_roles=["task_automation"],
    risk_level="MEDIUM",
    parameters={
        "task_ids": "List of task IDs to update",
        "action": "Action: complete, cancel, reassign, reschedule, update_priority",
        "action_params": "Parameters for the action",
    },
)
def bulk_update_tasks(
    task_ids: List[str],
    action: str,
    action_params: Optional[Dict] = None,
) -> ToolResult:
    """Perform bulk update on tasks."""
    params = action_params or {}

    valid_actions = ["complete", "cancel", "reassign", "reschedule", "update_priority"]
    if action not in valid_actions:
        return ToolResult.error(f"Invalid action. Must be one of: {', '.join(valid_actions)}")

    results = {
        "action": action,
        "action_params": params,
        "total_tasks": len(task_ids),
        "successful": 0,
        "failed": 0,
        "skipped": 0,
        "results": [],
    }

    for task_id in task_ids:
        # Get task current status
        task = execute_single("""
            SELECT id, title, status FROM tasks
            WHERE id = :id OR task_id = :id
        """, {"id": task_id})

        if not task:
            results["results"].append({
                "task_id": task_id,
                "status": "failed",
                "error": "Task not found",
            })
            results["failed"] += 1
            continue

        # Skip already completed/cancelled for certain actions
        if action in ["complete", "cancel"] and task.get("status") in ["completed", "cancelled"]:
            results["results"].append({
                "task_id": task_id,
                "status": "skipped",
                "reason": f"Task already {task.get('status')}",
            })
            results["skipped"] += 1
            continue

        try:
            update_data = {"task_id": task_id, "title": task.get("title")}

            if action == "complete":
                update_data["new_status"] = "completed"
                update_data["completed_at"] = datetime.now().isoformat()
            elif action == "cancel":
                update_data["new_status"] = "cancelled"
                update_data["cancelled_at"] = datetime.now().isoformat()
            elif action == "reassign":
                update_data["assigned_to"] = params.get("user_id")
            elif action == "reschedule":
                update_data["new_due_date"] = params.get("due_date")
            elif action == "update_priority":
                update_data["new_priority"] = params.get("priority")

            results["results"].append({
                "task_id": task_id,
                "status": "success",
                "update": update_data,
            })
            results["successful"] += 1

        except Exception as e:
            results["results"].append({
                "task_id": task_id,
                "status": "failed",
                "error": str(e),
            })
            results["failed"] += 1

    return ToolResult.success(
        data=results,
        message=f"Bulk {action}: {results['successful']}/{len(task_ids)} successful, {results['skipped']} skipped",
    )
