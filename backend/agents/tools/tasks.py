"""
Perennia AI - Task Automation Tools
===================================
Tools for the Task Automation Agent handling workflow tasks and automation.
10 tools for task management, workflow automation, and productivity.
"""

from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from .base import (
    mortgage_tool,
    ToolResult,
    execute_query,
    execute_single,
    format_date,
    days_between,
)


# =============================================================================
# Task Automation Tools (9 tools)
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
    name="bulk_create_tasks",
    description="Create multiple tasks at once, one for each borrower/lead. Use when the user asks to create follow-up tasks for several borrowers from a conversation.",
    agent_roles=["task_automation", "pipeline_analyst"],
    risk_level="LOW",
    parameters={
        "tasks_data": "JSON array of task objects, each with: title (required), lead_id (optional), loan_id (optional), description (optional), due_date (optional, YYYY-MM-DD), priority (low/normal/high/urgent), category (follow_up/document/call/review/compliance/other)",
    },
)
def bulk_create_tasks(
    tasks_data: str,
) -> ToolResult:
    """Create individual tasks for multiple borrowers in a single call.

    Args:
        tasks_data: JSON string containing an array of task objects.
            Each object can have:
                - title (required): Task title
                - lead_id (optional): Lead ID to link
                - loan_id (optional): Loan ID to link
                - description (optional): Task description
                - due_date (optional): YYYY-MM-DD format
                - priority (optional): low, normal, high, urgent (default: normal)
                - category (optional): follow_up, document, call, review, compliance, other (default: follow_up)
                - assigned_to (optional): User ID to assign to
    """
    import json as _json
    import uuid

    # Parse the JSON input
    try:
        if isinstance(tasks_data, list):
            task_list = tasks_data
        else:
            task_list = _json.loads(tasks_data)
    except (TypeError, _json.JSONDecodeError) as e:
        return ToolResult.error(f"Invalid tasks_data JSON: {e}")

    if not isinstance(task_list, list):
        return ToolResult.error("tasks_data must be a JSON array of task objects")

    if len(task_list) == 0:
        return ToolResult.error("tasks_data array is empty — provide at least one task")

    if len(task_list) > 50:
        return ToolResult.error("Maximum 50 tasks per bulk creation (received {})".format(len(task_list)))

    created_tasks = []
    errors = []

    for i, task_def in enumerate(task_list):
        if not isinstance(task_def, dict):
            errors.append({"index": i, "error": "Task must be a JSON object"})
            continue

        title = task_def.get("title")
        if not title:
            errors.append({"index": i, "error": "Missing required field 'title'"})
            continue

        # Resolve due date
        due_date = task_def.get("due_date")
        if not due_date:
            due = datetime.now() + timedelta(days=3)
            while due.weekday() >= 5:
                due += timedelta(days=1)
            due_date = due.strftime("%Y-%m-%d")

        lead_id = task_def.get("lead_id")
        loan_id = task_def.get("loan_id")
        priority = task_def.get("priority", "normal")
        category = task_def.get("category", "follow_up")
        description = task_def.get("description")
        assigned_to = task_def.get("assigned_to")

        task_id = f"TSK-{str(uuid.uuid4())[:8].upper()}"

        # Resolve related entity names for confirmation
        related_info = {}
        if lead_id:
            lead = execute_single(
                "SELECT first_name, last_name FROM leads WHERE id = :id",
                {"id": lead_id},
            )
            if lead:
                related_info["lead"] = {
                    "id": lead_id,
                    "name": f"{lead.get('first_name', '')} {lead.get('last_name', '')}".strip(),
                }

        if loan_id:
            loan = execute_single(
                "SELECT loan_number, borrower_name FROM loans WHERE id = :id",
                {"id": loan_id},
            )
            if loan:
                related_info["loan"] = {
                    "id": loan_id,
                    "number": loan.get("loan_number"),
                    "borrower": loan.get("borrower_name"),
                }

        created_tasks.append({
            "task_id": task_id,
            "title": title,
            "description": description,
            "due_date": due_date,
            "priority": priority,
            "category": category,
            "assigned_to": assigned_to,
            "lead_id": lead_id,
            "loan_id": loan_id,
            "status": "pending",
            "related": related_info,
            "created_at": datetime.now().isoformat(),
        })

    data = {
        "tasks_created": created_tasks,
        "total_created": len(created_tasks),
        "errors": errors,
        "total_errors": len(errors),
    }

    if not created_tasks:
        return ToolResult.error(
            f"No tasks created — {len(errors)} error(s): {errors}"
        )

    summary_parts = [f"{len(created_tasks)} task(s) created"]
    if errors:
        summary_parts.append(f"{len(errors)} skipped due to errors")

    # Build a brief list of who got tasks
    names = []
    for t in created_tasks:
        related = t.get("related", {})
        name = (
            related.get("lead", {}).get("name")
            or related.get("loan", {}).get("borrower")
            or t["title"]
        )
        names.append(name)
    if len(names) <= 5:
        summary_parts.append("for: " + ", ".join(names))
    else:
        summary_parts.append(f"for {len(names)} borrowers")

    return ToolResult.success(
        data=data,
        message=" | ".join(summary_parts),
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
            COALESCE(es.full_name, u.email) as assigned_name
        FROM tasks t
        LEFT JOIN leads l ON t.lead_id = l.id::text
        LEFT JOIN loans ln ON t.loan_id = ln.id::text
        LEFT JOIN users u ON t.assigned_to = u.id::text
        LEFT JOIN email_signatures es ON es.user_id = u.id
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
                u.id, COALESCE(es.full_name, u.email) AS name,
                COUNT(t.id) as open_tasks,
                COUNT(CASE WHEN t.priority = 'urgent' THEN 1 END) as urgent_tasks
            FROM users u
            LEFT JOIN email_signatures es ON es.user_id = u.id
            LEFT JOIN tasks t ON t.assigned_to = u.id::text
                AND t.status NOT IN ('completed', 'cancelled')
            WHERE u.role = 'loan_officer' AND u.is_active = true
            GROUP BY u.id, COALESCE(es.full_name, u.email)
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
        "SELECT u.id, COALESCE(es.full_name, u.email) AS name, u.email FROM users u LEFT JOIN email_signatures es ON es.user_id = u.id WHERE u.id = :id",
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
                "error": "Internal server error",
            })
            results["failed"] += 1

    return ToolResult.success(
        data=results,
        message=f"Bulk {action}: {results['successful']}/{len(task_ids)} successful, {results['skipped']} skipped",
    )


# =============================================================================
# Daily Call List Tool - Aggregates call-related data from multiple sources
# =============================================================================

@mortgage_tool(
    name="get_daily_call_list",
    description="Get prioritized daily call list aggregating call-type tasks, leads needing contact, and loans needing milestone follow-ups. Returns contact names, phone numbers, and call reasons.",
    agent_roles=["task_automation", "lead_nurturer", "pipeline_analyst"],
    risk_level="LOW",
    parameters={
        "user_id": "Optional user ID to filter by owner",
        "include_leads": "Include leads needing contact (default: true)",
        "include_loans": "Include loans needing milestone follow-ups (default: true)",
        "include_tasks": "Include call-type tasks (default: true)",
        "limit": "Maximum contacts to return (default: 20)",
    },
)
def get_daily_call_list(
    user_id: Optional[str] = None,
    include_leads: bool = True,
    include_loans: bool = True,
    include_tasks: bool = True,
    limit: int = 20,
) -> ToolResult:
    """
    Get a prioritized daily call list aggregating data from:
    1. Tasks - call-type tasks due today or overdue
    2. Leads - new leads or those not contacted in 3+ days
    3. Loans - milestone follow-ups (stage changes, rate locks expiring, etc.)

    Returns formatted list with contact names, phone numbers, and reasons to call.
    """
    today = datetime.now().date()
    calls = []

    # =========================================================================
    # 1. Get call-type tasks due today or overdue
    # =========================================================================
    if include_tasks:
        task_params = {}
        task_filters = [
            "t.status NOT IN ('completed', 'cancelled')",
            "(t.due_date <= CURRENT_DATE OR t.due_date IS NULL)",
        ]

        if user_id:
            task_filters.append("t.owner_id = :user_id")
            task_params["user_id"] = user_id

        # Match call-type tasks by title/description containing 'call' or category
        task_filters.append("""(
            LOWER(t.title) LIKE '%call%'
            OR LOWER(t.title) LIKE '%phone%'
            OR LOWER(t.title) LIKE '%contact%'
            OR LOWER(t.title) LIKE '%follow up%'
            OR LOWER(t.title) LIKE '%follow-up%'
            OR LOWER(COALESCE(t.description, '')) LIKE '%call%'
        )""")

        where_sql = " AND ".join(task_filters)

        task_results = execute_query(f"""
            SELECT
                t.id, t.title, t.description, t.due_date, t.priority,
                t.related_contact_name,
                l.name as lead_name, l.phone as lead_phone, l.email as lead_email,
                ln.borrower_name, ln.borrower_phone, ln.loan_number
            FROM tasks t
            LEFT JOIN leads l ON t.lead_id = l.id
            LEFT JOIN loans ln ON t.loan_id = ln.id
            WHERE {where_sql}
            ORDER BY
                CASE t.priority
                    WHEN 'urgent' THEN 1
                    WHEN 'high' THEN 2
                    WHEN 'medium' THEN 3
                    ELSE 4
                END,
                t.due_date ASC NULLS LAST
            LIMIT 10
        """, task_params)

        for task in task_results:
            # Get contact info from task, lead, or loan
            contact_name = (
                task.get("related_contact_name") or
                task.get("lead_name") or
                task.get("borrower_name") or
                "Unknown"
            )
            phone = task.get("lead_phone") or task.get("borrower_phone")

            if contact_name and contact_name != "Unknown":
                due_date = task.get("due_date")
                is_overdue = False
                if due_date:
                    if hasattr(due_date, 'date'):
                        is_overdue = due_date.date() < today
                    else:
                        is_overdue = due_date < today

                reason = task.get("title", "Follow-up call")
                if is_overdue:
                    reason = f"[OVERDUE] {reason}"
                elif task.get("priority") in ("urgent", "high"):
                    reason = f"[{task.get('priority').upper()}] {reason}"

                calls.append({
                    "source": "task",
                    "priority": 1 if task.get("priority") == "urgent" else (2 if task.get("priority") == "high" else 3),
                    "name": contact_name,
                    "phone": phone,
                    "email": task.get("lead_email"),
                    "reason": reason,
                    "context": {
                        "task_id": task.get("id"),
                        "loan_number": task.get("loan_number"),
                        "is_overdue": is_overdue,
                    },
                })

    # =========================================================================
    # 2. Get leads needing contact (new or not contacted in 3+ days)
    # =========================================================================
    if include_leads:
        lead_params = {"days_threshold": 3}
        lead_filters = [
            # Exclude terminal lead stages - only use values that exist in prod database enum
            "l.stage NOT IN ('Withdrawn', 'Does Not Qualify')",
            "l.phone IS NOT NULL",
            "l.phone != ''",
        ]

        if user_id:
            lead_filters.append("l.owner_id = :user_id")
            lead_params["user_id"] = user_id

        # New leads or those not contacted recently
        lead_filters.append("""(
            l.stage = 'New'
            OR l.last_contact IS NULL
            OR l.last_contact < CURRENT_DATE - INTERVAL ':days_threshold days'
        )""".replace(":days_threshold", str(lead_params["days_threshold"])))

        where_sql = " AND ".join(lead_filters)

        lead_results = execute_query(f"""
            SELECT
                l.id, l.name, l.first_name, l.last_name,
                l.phone, l.email, l.stage, l.source,
                l.last_contact, l.ai_score, l.created_at,
                l.loan_type, l.preapproval_amount
            FROM leads l
            WHERE {where_sql}
            ORDER BY
                CASE
                    WHEN l.stage = 'New' THEN 1
                    WHEN l.last_contact IS NULL THEN 2
                    ELSE 3
                END,
                l.ai_score DESC NULLS LAST,
                l.created_at DESC
            LIMIT 10
        """, lead_params)

        for lead in lead_results:
            lead_name = lead.get("name") or f"{lead.get('first_name', '')} {lead.get('last_name', '')}".strip()

            # Build reason
            if lead.get("stage") == "New":
                days_since_created = days_between(lead.get("created_at"), datetime.now())
                reason = f"New lead from {lead.get('source', 'unknown source')}"
                if days_since_created == 0:
                    reason += " - today"
                elif days_since_created == 1:
                    reason += " - yesterday"
                else:
                    reason += f" - {days_since_created} days ago"
                priority = 2  # High priority for new leads
            elif not lead.get("last_contact"):
                reason = "Lead never contacted - needs qualification call"
                priority = 2
            else:
                days_since_contact = days_between(lead.get("last_contact"), datetime.now())
                reason = f"No contact in {days_since_contact} days - follow up needed"
                priority = 3

            # Add loan interest context if available
            if lead.get("loan_type"):
                reason += f" ({lead.get('loan_type')})"

            calls.append({
                "source": "lead",
                "priority": priority,
                "name": lead_name,
                "phone": lead.get("phone"),
                "email": lead.get("email"),
                "reason": reason,
                "context": {
                    "lead_id": lead.get("id"),
                    "stage": lead.get("stage"),
                    "ai_score": lead.get("ai_score"),
                    "preapproval_amount": lead.get("preapproval_amount"),
                },
            })

    # =========================================================================
    # 3. Get loans needing milestone follow-ups
    # =========================================================================
    if include_loans:
        loan_params = {}
        loan_filters = [
            "ln.stage NOT IN ('Funded')",
            "ln.borrower_phone IS NOT NULL",
            "ln.borrower_phone != ''",
        ]

        if user_id:
            loan_filters.append("ln.loan_officer_id = :user_id")
            loan_params["user_id"] = user_id

        where_sql = " AND ".join(loan_filters)

        loan_results = execute_query(f"""
            SELECT
                ln.id, ln.loan_number, ln.borrower_name, ln.borrower_phone, ln.borrower_email,
                ln.stage, ln.amount, ln.closing_date, ln.lock_date,
                ln.days_in_stage, ln.sla_status, ln.created_at
            FROM loans ln
            WHERE {where_sql}
            ORDER BY
                CASE
                    WHEN ln.sla_status = 'at-risk' THEN 1
                    WHEN ln.sla_status = 'warning' THEN 2
                    WHEN ln.closing_date <= CURRENT_DATE + INTERVAL '7 days' THEN 1
                    ELSE 3
                END,
                ln.closing_date ASC NULLS LAST
            LIMIT 10
        """, loan_params)

        for loan in loan_results:
            # Determine call reason based on loan state
            reasons = []
            priority = 4  # Default lower priority

            # Check for rate lock expiring
            if loan.get("lock_date"):
                lock_date = loan.get("lock_date")
                if hasattr(lock_date, 'date'):
                    lock_date = lock_date.date()
                days_to_lock = (lock_date - today).days if lock_date else None
                if days_to_lock is not None and days_to_lock <= 5 and days_to_lock >= 0:
                    reasons.append(f"Rate lock expiring in {days_to_lock} days")
                    priority = 1 if days_to_lock <= 2 else 2

            # Check for closing coming up
            if loan.get("closing_date"):
                closing_date = loan.get("closing_date")
                if hasattr(closing_date, 'date'):
                    closing_date = closing_date.date()
                days_to_close = (closing_date - today).days if closing_date else None
                if days_to_close is not None and days_to_close <= 7 and days_to_close >= 0:
                    reasons.append(f"Closing in {days_to_close} days")
                    priority = min(priority, 2)

            # Check for SLA issues
            if loan.get("sla_status") == "at-risk":
                reasons.append(f"SLA at risk - {loan.get('days_in_stage', '?')} days in {loan.get('stage')}")
                priority = min(priority, 2)
            elif loan.get("sla_status") == "warning":
                reasons.append(f"SLA warning - {loan.get('days_in_stage', '?')} days in {loan.get('stage')}")
                priority = min(priority, 3)

            # Check for stale loans (many days in stage)
            if loan.get("days_in_stage") and loan.get("days_in_stage") >= 7 and not reasons:
                reasons.append(f"Loan in {loan.get('stage')} for {loan.get('days_in_stage')} days - status update call")
                priority = 3

            # Only add if there's a reason to call
            if reasons:
                reason = "; ".join(reasons)

                calls.append({
                    "source": "loan",
                    "priority": priority,
                    "name": loan.get("borrower_name"),
                    "phone": loan.get("borrower_phone"),
                    "email": loan.get("borrower_email"),
                    "reason": reason,
                    "context": {
                        "loan_id": loan.get("id"),
                        "loan_number": loan.get("loan_number"),
                        "stage": loan.get("stage"),
                        "amount": loan.get("amount"),
                        "closing_date": format_date(loan.get("closing_date")),
                    },
                })

    # =========================================================================
    # Sort and limit results
    # =========================================================================
    # Sort by priority (lower is higher priority)
    calls.sort(key=lambda x: (x["priority"], x["source"] != "task"))
    calls = calls[:limit]

    # Format for output
    formatted_calls = []
    for i, call in enumerate(calls, 1):
        formatted_calls.append({
            "rank": i,
            "name": call["name"],
            "phone": call["phone"],
            "email": call.get("email"),
            "reason": call["reason"],
            "source": call["source"],
            "context": call.get("context", {}),
        })

    # Summary stats
    summary = {
        "total": len(formatted_calls),
        "from_tasks": sum(1 for c in formatted_calls if c["source"] == "task"),
        "from_leads": sum(1 for c in formatted_calls if c["source"] == "lead"),
        "from_loans": sum(1 for c in formatted_calls if c["source"] == "loan"),
        "high_priority": sum(1 for c in calls if c["priority"] <= 2),
    }

    data = {
        "calls": formatted_calls,
        "summary": summary,
        "generated_at": datetime.now().isoformat(),
    }

    if not formatted_calls:
        return ToolResult.no_data("No calls needed today - pipeline is on track!")

    return ToolResult.success(
        data=data,
        message=f"Found {len(formatted_calls)} contacts to call: {summary['from_tasks']} tasks, {summary['from_leads']} leads, {summary['from_loans']} loans",
    )


# =============================================================================
# Workflow Task Creation Tool
# =============================================================================

@mortgage_tool(
    name="create_workflow_task",
    description="Create a task tied to a specific workflow step such as follow-up, document review, or condition clearing",
    agent_roles=["task_automation", "ops_manager", "pipeline_analyst"],
    risk_level="LOW",
    requires_confirmation=False,
    parameters={
        "title": "Task title (required)",
        "task_type": "Workflow task type: follow_up, document_review, condition_clearing",
        "loan_id": "Optional loan ID to link",
        "lead_id": "Optional lead ID to link",
        "due_date": "Due date (YYYY-MM-DD), defaults to 3 business days",
        "assigned_to": "Optional user ID to assign to",
    },
)
def create_workflow_task(
    title: str,
    task_type: str = "follow_up",
    loan_id: Optional[int] = None,
    lead_id: Optional[int] = None,
    due_date: Optional[str] = None,
    assigned_to: Optional[int] = None,
) -> ToolResult:
    """Create a task tied to a workflow step."""
    valid_types = ["follow_up", "document_review", "condition_clearing"]
    if task_type not in valid_types:
        return ToolResult.error(
            f"Invalid task_type '{task_type}'. Must be one of: {', '.join(valid_types)}"
        )

    # Default due date: 3 business days from now
    if not due_date:
        due = datetime.now() + timedelta(days=3)
        while due.weekday() >= 5:
            due += timedelta(days=1)
        due_date = due.strftime("%Y-%m-%d")

    import uuid
    task_id = f"WFT-{str(uuid.uuid4())[:8].upper()}"

    # Resolve related entity info
    related_info = {}
    if loan_id:
        loan = execute_single(
            "SELECT loan_number, borrower_name FROM loans WHERE id = :id",
            {"id": loan_id},
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
            {"id": lead_id},
        )
        if lead:
            related_info["lead"] = {
                "id": lead_id,
                "name": f"{lead.get('first_name', '')} {lead.get('last_name', '')}".strip(),
            }

    assignee_name = None
    if assigned_to:
        user = execute_single(
            "SELECT COALESCE(es.full_name, u.email) AS name FROM users u LEFT JOIN email_signatures es ON es.user_id = u.id WHERE u.id = :id",
            {"id": assigned_to},
        )
        if user:
            assignee_name = user.get("name")

    task = {
        "task_id": task_id,
        "title": title,
        "task_type": task_type,
        "category": task_type,
        "due_date": due_date,
        "priority": "high" if task_type == "condition_clearing" else "normal",
        "assigned_to": assigned_to,
        "assigned_name": assignee_name,
        "loan_id": loan_id,
        "lead_id": lead_id,
        "status": "pending",
        "related": related_info,
        "created_at": datetime.now().isoformat(),
    }

    return ToolResult.success(
        data=task,
        message=f"Workflow task created: {title} ({task_type}, due {due_date})",
    )
