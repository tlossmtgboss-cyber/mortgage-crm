"""
Task & Calendar Agent

Specialized agent for task and calendar management with 8 tools:
1. get_tasks - Get tasks with filtering
2. create_task - Create a new task
3. update_task - Update task status/details
4. get_calendar - Get calendar events
5. schedule_appointment - Schedule a new appointment
6. get_due_today - Get all items due today
7. reschedule_item - Reschedule task or appointment
8. get_overdue - Get overdue items needing attention
"""

import logging
from typing import Any, Dict, Optional, List
from datetime import datetime, date, timedelta
from pydantic import BaseModel, Field
from sqlalchemy import text

logger = logging.getLogger(__name__)

from .base import (
    SpecializedAgent,
    AgentTool,
    AgentContext,
    ToolCategory,
    RiskLevel,
    ToolResult,
    AgentRegistry
)


# ============================================================================
# INPUT SCHEMAS
# ============================================================================

class GetTasksInput(BaseModel):
    """Input schema for get_tasks tool"""
    status: Optional[str] = Field(None, description="Filter by status: pending, in_progress, completed, cancelled")
    priority: Optional[str] = Field(None, description="Filter by priority: low, normal, high, urgent")
    entity_type: Optional[str] = Field(None, description="Filter by entity type: lead, loan, contact")
    entity_id: Optional[int] = Field(None, description="Filter by specific entity ID")
    assigned_to: Optional[int] = Field(None, description="Filter by assigned user ID")
    due_before: Optional[str] = Field(None, description="Filter tasks due before date (ISO format)")
    limit: int = Field(default=50, description="Maximum tasks to return")


class CreateTaskInput(BaseModel):
    """Input schema for create_task tool"""
    title: str = Field(..., description="Task title")
    description: Optional[str] = Field(None, description="Task description")
    entity_type: Optional[str] = Field(None, description="Related entity type: lead, loan, contact")
    entity_id: Optional[int] = Field(None, description="Related entity ID")
    due_date: Optional[str] = Field(None, description="Due date (ISO format)")
    due_time: Optional[str] = Field(None, description="Due time (HH:MM format)")
    priority: str = Field(default="normal", description="Priority: low, normal, high, urgent")
    task_type: str = Field(default="follow_up", description="Task type: follow_up, call, email, document_request, review, appointment")
    assigned_to: Optional[int] = Field(None, description="User ID to assign to")


class UpdateTaskInput(BaseModel):
    """Input schema for update_task tool"""
    task_id: int = Field(..., description="Task ID to update")
    status: Optional[str] = Field(None, description="New status: pending, in_progress, completed, cancelled")
    priority: Optional[str] = Field(None, description="New priority")
    due_date: Optional[str] = Field(None, description="New due date")
    notes: Optional[str] = Field(None, description="Notes to add")


class GetCalendarInput(BaseModel):
    """Input schema for get_calendar tool"""
    start_date: Optional[str] = Field(None, description="Start date (ISO format), defaults to today")
    end_date: Optional[str] = Field(None, description="End date (ISO format), defaults to 7 days out")
    include_tasks: bool = Field(default=True, description="Include tasks with due dates")
    include_appointments: bool = Field(default=True, description="Include appointments")


class ScheduleAppointmentInput(BaseModel):
    """Input schema for schedule_appointment tool"""
    title: str = Field(..., description="Appointment title")
    start_time: str = Field(..., description="Start datetime (ISO format)")
    end_time: Optional[str] = Field(None, description="End datetime (ISO format)")
    duration_minutes: int = Field(default=30, description="Duration if end_time not specified")
    entity_type: Optional[str] = Field(None, description="Related entity type: lead, loan, contact")
    entity_id: Optional[int] = Field(None, description="Related entity ID")
    location: Optional[str] = Field(None, description="Meeting location or video link")
    attendees: Optional[List[str]] = Field(None, description="List of attendee emails")
    notes: Optional[str] = Field(None, description="Appointment notes")


class GetDueTodayInput(BaseModel):
    """Input schema for get_due_today tool"""
    include_overdue: bool = Field(default=True, description="Include overdue items")
    user_id: Optional[int] = Field(None, description="Filter by user ID")


class RescheduleItemInput(BaseModel):
    """Input schema for reschedule_item tool"""
    item_type: str = Field(..., description="Item type: task or appointment")
    item_id: int = Field(..., description="Item ID to reschedule")
    new_date: str = Field(..., description="New date (ISO format)")
    new_time: Optional[str] = Field(None, description="New time (HH:MM format)")
    reason: Optional[str] = Field(None, description="Reason for rescheduling")


class GetOverdueInput(BaseModel):
    """Input schema for get_overdue tool"""
    user_id: Optional[int] = Field(None, description="Filter by user ID")
    entity_type: Optional[str] = Field(None, description="Filter by entity type")
    limit: int = Field(default=50, description="Maximum items to return")


# ============================================================================
# TASK CALENDAR AGENT
# ============================================================================

@AgentRegistry.register
class TaskCalendarAgent(SpecializedAgent):
    """
    Specialized agent for task and calendar management.

    Handles task creation, scheduling, calendar management,
    and deadline tracking.
    """

    @property
    def name(self) -> str:
        return "TaskCalendarAgent"

    @property
    def description(self) -> str:
        return "Manages tasks, appointments, and calendar events including scheduling and deadline tracking"

    def _register_tools(self):
        """Register all task and calendar tools"""

        # Tool 1: Get Tasks
        self.register_tool(AgentTool(
            name="get_tasks",
            description="Get tasks with optional filtering by status, priority, entity, or due date. "
                       "Returns task list with details and counts.",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._get_tasks,
            input_schema=GetTasksInput
        ))

        # Tool 2: Create Task
        self.register_tool(AgentTool(
            name="create_task",
            description="Create a new task with optional entity association. "
                       "Supports priorities, due dates, and assignment.",
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.LOW,
            handler=self._create_task,
            input_schema=CreateTaskInput
        ))

        # Tool 3: Update Task
        self.register_tool(AgentTool(
            name="update_task",
            description="Update an existing task's status, priority, due date, or add notes. "
                       "Use to mark tasks complete or modify details.",
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.LOW,
            handler=self._update_task,
            input_schema=UpdateTaskInput
        ))

        # Tool 4: Get Calendar
        self.register_tool(AgentTool(
            name="get_calendar",
            description="Get calendar view with tasks and appointments for a date range. "
                       "Useful for schedule overview and availability checking.",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._get_calendar,
            input_schema=GetCalendarInput
        ))

        # Tool 5: Schedule Appointment
        self.register_tool(AgentTool(
            name="schedule_appointment",
            description="Schedule a new appointment or meeting. "
                       "Can be linked to leads or loans with optional attendees.",
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.MEDIUM,
            handler=self._schedule_appointment,
            input_schema=ScheduleAppointmentInput
        ))

        # Tool 6: Get Due Today
        self.register_tool(AgentTool(
            name="get_due_today",
            description="Get all tasks and appointments due today. "
                       "Essential for daily planning and prioritization.",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._get_due_today,
            input_schema=GetDueTodayInput
        ))

        # Tool 7: Reschedule Item
        self.register_tool(AgentTool(
            name="reschedule_item",
            description="Reschedule a task or appointment to a new date/time. "
                       "Records the reason for rescheduling.",
            category=ToolCategory.ACTION,
            risk_level=RiskLevel.LOW,
            handler=self._reschedule_item,
            input_schema=RescheduleItemInput
        ))

        # Tool 8: Get Overdue
        self.register_tool(AgentTool(
            name="get_overdue",
            description="Get all overdue tasks and past appointments. "
                       "Critical for identifying items needing immediate attention.",
            category=ToolCategory.QUERY,
            risk_level=RiskLevel.LOW,
            handler=self._get_overdue,
            input_schema=GetOverdueInput
        ))

    # ========================================================================
    # TOOL IMPLEMENTATIONS
    # ========================================================================

    async def _get_tasks(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Get tasks with filtering"""
        from database import SessionLocal

        db = SessionLocal()
        try:
            org_id = self.context.get("organization_id")
            conditions = ["1=1"]
            params = {"limit": input_data.get("limit", 50)}

            if org_id:
                conditions.append("organization_id = :org_id")
                params["org_id"] = org_id

            if input_data.get("status"):
                conditions.append("status = :status")
                params["status"] = input_data["status"]

            if input_data.get("priority"):
                conditions.append("priority = :priority")
                params["priority"] = input_data["priority"]

            if input_data.get("entity_type"):
                conditions.append("entity_type = :entity_type")
                params["entity_type"] = input_data["entity_type"]

            if input_data.get("entity_id"):
                conditions.append("entity_id = :entity_id")
                params["entity_id"] = input_data["entity_id"]

            if input_data.get("assigned_to"):
                conditions.append("assigned_to = :assigned_to")
                params["assigned_to"] = input_data["assigned_to"]

            if input_data.get("due_before"):
                conditions.append("due_date <= :due_before")
                params["due_before"] = input_data["due_before"]

            where_clause = " AND ".join(conditions)

            query = text(f"""
                SELECT
                    t.id, t.title, t.description, t.status, t.priority,
                    t.task_type, t.entity_type, t.entity_id,
                    t.due_date, t.completed_at, t.assigned_to,
                    t.created_at, t.updated_at,
                    CASE
                        WHEN t.due_date < CURRENT_DATE AND t.status != 'completed' THEN true
                        ELSE false
                    END as is_overdue
                FROM tasks t
                WHERE {where_clause}
                ORDER BY
                    CASE WHEN t.status = 'completed' THEN 1 ELSE 0 END,
                    t.due_date ASC NULLS LAST,
                    CASE t.priority
                        WHEN 'urgent' THEN 0
                        WHEN 'high' THEN 1
                        WHEN 'normal' THEN 2
                        ELSE 3
                    END
                LIMIT :limit
            """)

            results = db.execute(query, params).fetchall()

            tasks = []
            overdue_count = 0
            for r in results:
                if r.is_overdue:
                    overdue_count += 1
                tasks.append({
                    "id": r.id,
                    "title": r.title,
                    "description": r.description,
                    "status": r.status,
                    "priority": r.priority,
                    "task_type": r.task_type,
                    "entity_type": r.entity_type,
                    "entity_id": r.entity_id,
                    "due_date": r.due_date.isoformat() if r.due_date else None,
                    "is_overdue": r.is_overdue,
                    "assigned_to": r.assigned_to
                })

            # Get status counts
            org_clause = "WHERE organization_id = :org_id" if org_id else ""
            count_query = text(f"""
                SELECT status, COUNT(*) as count
                FROM tasks
                {org_clause}
                GROUP BY status
            """)
            counts = db.execute(count_query, {"org_id": org_id} if org_id else {}).fetchall()
            status_counts = {c.status: c.count for c in counts}

            return ToolResult(
                success=True,
                data={
                    "tasks": tasks,
                    "count": len(tasks),
                    "overdue_count": overdue_count,
                    "status_counts": status_counts
                },
                message=f"Found {len(tasks)} tasks, {overdue_count} overdue"
            )

        except Exception as e:
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _create_task(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Create a new task"""
        from database import SessionLocal

        db = SessionLocal()
        try:
            org_id = self.context.get("organization_id")

            query = text("""
                INSERT INTO tasks (
                    title, description, entity_type, entity_id,
                    due_date, priority, task_type, status,
                    assigned_to, created_by, organization_id, created_at
                ) VALUES (
                    :title, :description, :entity_type, :entity_id,
                    :due_date, :priority, :task_type, 'pending',
                    :assigned_to, :created_by, :organization_id, CURRENT_TIMESTAMP
                )
                RETURNING id, title, due_date
            """)

            # Parse due date and time
            due_date = None
            if input_data.get("due_date"):
                due_date = input_data["due_date"]
                if input_data.get("due_time"):
                    due_date = f"{due_date}T{input_data['due_time']}:00"

            result = db.execute(query, {
                "title": input_data["title"],
                "description": input_data.get("description"),
                "entity_type": input_data.get("entity_type"),
                "entity_id": input_data.get("entity_id"),
                "due_date": due_date,
                "priority": input_data.get("priority", "normal"),
                "task_type": input_data.get("task_type", "follow_up"),
                "assigned_to": input_data.get("assigned_to", context.get("user_id")),
                "created_by": context.get("user_id", 1),
                "organization_id": org_id
            }).fetchone()

            db.commit()

            self.audit_log(
                "create_task",
                entity_type="task",
                entity_id=result.id,
                details={"title": input_data["title"], "priority": input_data.get("priority", "normal")}
            )

            return ToolResult(
                success=True,
                data={
                    "task_id": result.id,
                    "title": result.title,
                    "due_date": result.due_date.isoformat() if result.due_date else None
                },
                message=f"Task '{result.title}' created successfully"
            )

        except Exception as e:
            db.rollback()
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _update_task(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Update an existing task"""
        from database import SessionLocal

        task_id = input_data["task_id"]
        db = SessionLocal()

        try:
            org_id = self.context.get("organization_id")
            org_clause = "AND organization_id = :org_id" if org_id else ""
            task_params = {"task_id": task_id}
            if org_id:
                task_params["org_id"] = org_id

            # Get current task
            current = db.execute(
                text(f"SELECT * FROM tasks WHERE id = :task_id {org_clause}"),
                task_params
            ).fetchone()

            if not current:
                return ToolResult(success=False, error=f"Task {task_id} not found")

            # Build update
            updates = ["updated_at = CURRENT_TIMESTAMP"]
            params = {"task_id": task_id}
            if org_id:
                params["org_id"] = org_id

            if input_data.get("status"):
                updates.append("status = :status")
                params["status"] = input_data["status"]
                if input_data["status"] == "completed":
                    updates.append("completed_at = CURRENT_TIMESTAMP")

            if input_data.get("priority"):
                updates.append("priority = :priority")
                params["priority"] = input_data["priority"]

            if input_data.get("due_date"):
                updates.append("due_date = :due_date")
                params["due_date"] = input_data["due_date"]

            if input_data.get("notes"):
                updates.append("notes = COALESCE(notes, '') || :notes")
                params["notes"] = f"\n[{datetime.now().isoformat()}] {input_data['notes']}"

            query = text(f"""
                UPDATE tasks
                SET {', '.join(updates)}
                WHERE id = :task_id {org_clause}
                RETURNING id, title, status, priority, due_date
            """)

            result = db.execute(query, params).fetchone()
            db.commit()

            self.audit_log(
                "update_task",
                entity_type="task",
                entity_id=task_id,
                details={"status": input_data.get("status"), "priority": input_data.get("priority")}
            )

            return ToolResult(
                success=True,
                data={
                    "task_id": result.id,
                    "title": result.title,
                    "status": result.status,
                    "priority": result.priority,
                    "due_date": result.due_date.isoformat() if result.due_date else None
                },
                message=f"Task '{result.title}' updated successfully"
            )

        except Exception as e:
            db.rollback()
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _get_calendar(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Get calendar view with tasks and appointments"""
        from database import SessionLocal

        db = SessionLocal()
        try:
            org_id = self.context.get("organization_id")
            start_date = input_data.get("start_date", date.today().isoformat())
            end_date = input_data.get("end_date", (date.today() + timedelta(days=7)).isoformat())

            org_clause = "AND organization_id = :org_id" if org_id else ""
            base_params = {"start_date": start_date, "end_date": end_date}
            if org_id:
                base_params["org_id"] = org_id

            calendar_items = []

            # Get tasks with due dates
            if input_data.get("include_tasks", True):
                tasks_query = text(f"""
                    SELECT
                        'task' as item_type,
                        id, title, due_date as start_time, NULL as end_time,
                        priority, status, entity_type, entity_id
                    FROM tasks
                    WHERE due_date BETWEEN :start_date AND :end_date
                        AND status != 'cancelled'
                        {org_clause}
                    ORDER BY due_date
                """)
                tasks = db.execute(tasks_query, base_params).fetchall()

                for t in tasks:
                    calendar_items.append({
                        "type": "task",
                        "id": t.id,
                        "title": t.title,
                        "start": t.start_time.isoformat() if t.start_time else None,
                        "end": None,
                        "priority": t.priority,
                        "status": t.status,
                        "entity_type": t.entity_type,
                        "entity_id": t.entity_id
                    })

            # Get appointments
            if input_data.get("include_appointments", True):
                appt_query = text(f"""
                    SELECT
                        'appointment' as item_type,
                        id, title, start_time, end_time,
                        location, entity_type, entity_id, status
                    FROM appointments
                    WHERE start_time BETWEEN :start_date AND :end_date
                        AND status != 'cancelled'
                        {org_clause}
                    ORDER BY start_time
                """)
                appointments = db.execute(appt_query, base_params).fetchall()

                for a in appointments:
                    calendar_items.append({
                        "type": "appointment",
                        "id": a.id,
                        "title": a.title,
                        "start": a.start_time.isoformat() if a.start_time else None,
                        "end": a.end_time.isoformat() if a.end_time else None,
                        "location": a.location,
                        "status": a.status,
                        "entity_type": a.entity_type,
                        "entity_id": a.entity_id
                    })

            # Sort by start time
            calendar_items.sort(key=lambda x: x["start"] or "")

            # Group by date
            by_date = {}
            for item in calendar_items:
                if item["start"]:
                    item_date = item["start"][:10]
                    if item_date not in by_date:
                        by_date[item_date] = []
                    by_date[item_date].append(item)

            return ToolResult(
                success=True,
                data={
                    "start_date": start_date,
                    "end_date": end_date,
                    "items": calendar_items,
                    "by_date": by_date,
                    "total_count": len(calendar_items)
                },
                message=f"Calendar: {len(calendar_items)} items from {start_date} to {end_date}"
            )

        except Exception as e:
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _schedule_appointment(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Schedule a new appointment"""
        from database import SessionLocal

        db = SessionLocal()
        try:
            org_id = self.context.get("organization_id")
            start_time = datetime.fromisoformat(input_data["start_time"])

            if input_data.get("end_time"):
                end_time = datetime.fromisoformat(input_data["end_time"])
            else:
                duration = input_data.get("duration_minutes", 30)
                end_time = start_time + timedelta(minutes=duration)

            query = text("""
                INSERT INTO appointments (
                    title, start_time, end_time, entity_type, entity_id,
                    location, notes, status, created_by, organization_id, created_at
                ) VALUES (
                    :title, :start_time, :end_time, :entity_type, :entity_id,
                    :location, :notes, 'scheduled', :created_by, :organization_id, CURRENT_TIMESTAMP
                )
                RETURNING id, title, start_time, end_time
            """)

            result = db.execute(query, {
                "title": input_data["title"],
                "start_time": start_time,
                "end_time": end_time,
                "entity_type": input_data.get("entity_type"),
                "entity_id": input_data.get("entity_id"),
                "location": input_data.get("location"),
                "notes": input_data.get("notes"),
                "created_by": context.get("user_id", 1),
                "organization_id": org_id
            }).fetchone()

            db.commit()

            self.audit_log(
                "schedule_appointment",
                entity_type="appointment",
                entity_id=result.id,
                details={"title": input_data["title"], "start_time": start_time.isoformat()}
            )

            return ToolResult(
                success=True,
                data={
                    "appointment_id": result.id,
                    "title": result.title,
                    "start_time": result.start_time.isoformat(),
                    "end_time": result.end_time.isoformat() if result.end_time else None
                },
                message=f"Appointment '{result.title}' scheduled for {result.start_time.strftime('%m/%d/%Y %I:%M %p')}"
            )

        except Exception as e:
            db.rollback()
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _get_due_today(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Get all items due today"""
        from database import SessionLocal

        db = SessionLocal()
        try:
            org_id = self.context.get("organization_id")
            user_id = input_data.get("user_id", context.get("user_id"))
            include_overdue = input_data.get("include_overdue", True)

            params = {}
            user_filter = ""
            org_filter = ""
            if user_id:
                user_filter = "AND assigned_to = :user_id"
                params["user_id"] = user_id
            if org_id:
                org_filter = "AND organization_id = :org_id"
                params["org_id"] = org_id

            # Get tasks due today
            if include_overdue:
                date_condition = "due_date <= CURRENT_DATE"
            else:
                date_condition = "due_date = CURRENT_DATE"

            tasks_query = text(f"""
                SELECT
                    id, title, description, priority, task_type,
                    due_date, entity_type, entity_id,
                    CASE WHEN due_date < CURRENT_DATE THEN true ELSE false END as is_overdue
                FROM tasks
                WHERE {date_condition}
                    AND status NOT IN ('completed', 'cancelled')
                    {user_filter}
                    {org_filter}
                ORDER BY
                    is_overdue DESC,
                    CASE priority
                        WHEN 'urgent' THEN 0
                        WHEN 'high' THEN 1
                        WHEN 'normal' THEN 2
                        ELSE 3
                    END,
                    due_date
            """)

            tasks = db.execute(tasks_query, params).fetchall()

            # Get appointments today
            appt_params = {}
            appt_org_filter = ""
            if org_id:
                appt_org_filter = "AND organization_id = :org_id"
                appt_params["org_id"] = org_id

            appt_query = text(f"""
                SELECT
                    id, title, start_time, end_time, location,
                    entity_type, entity_id
                FROM appointments
                WHERE DATE(start_time) = CURRENT_DATE
                    AND status != 'cancelled'
                    {appt_org_filter}
                ORDER BY start_time
            """)

            appointments = db.execute(appt_query, appt_params).fetchall()

            task_list = []
            overdue_count = 0
            for t in tasks:
                if t.is_overdue:
                    overdue_count += 1
                task_list.append({
                    "id": t.id,
                    "title": t.title,
                    "priority": t.priority,
                    "task_type": t.task_type,
                    "due_date": t.due_date.isoformat() if t.due_date else None,
                    "is_overdue": t.is_overdue,
                    "entity_type": t.entity_type,
                    "entity_id": t.entity_id
                })

            appt_list = [
                {
                    "id": a.id,
                    "title": a.title,
                    "start_time": a.start_time.isoformat() if a.start_time else None,
                    "end_time": a.end_time.isoformat() if a.end_time else None,
                    "location": a.location,
                    "entity_type": a.entity_type,
                    "entity_id": a.entity_id
                }
                for a in appointments
            ]

            return ToolResult(
                success=True,
                data={
                    "date": date.today().isoformat(),
                    "tasks": task_list,
                    "appointments": appt_list,
                    "task_count": len(task_list),
                    "appointment_count": len(appt_list),
                    "overdue_count": overdue_count
                },
                message=f"Today: {len(task_list)} tasks ({overdue_count} overdue), {len(appt_list)} appointments"
            )

        except Exception as e:
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _reschedule_item(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Reschedule a task or appointment"""
        from database import SessionLocal

        item_type = input_data["item_type"]
        item_id = input_data["item_id"]
        new_date = input_data["new_date"]
        new_time = input_data.get("new_time")
        reason = input_data.get("reason", "Rescheduled by AI agent")

        db = SessionLocal()
        try:
            org_id = self.context.get("organization_id")
            org_clause = "AND organization_id = :org_id" if org_id else ""

            if item_type == "task":
                # Reschedule task
                new_due = new_date
                if new_time:
                    new_due = f"{new_date}T{new_time}:00"

                task_params = {
                    "item_id": item_id,
                    "new_due": new_due,
                    "reschedule_note": f"\n[{datetime.now().isoformat()}] Rescheduled: {reason}"
                }
                if org_id:
                    task_params["org_id"] = org_id

                query = text(f"""
                    UPDATE tasks
                    SET due_date = :new_due,
                        notes = COALESCE(notes, '') || :reschedule_note,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :item_id {org_clause}
                    RETURNING id, title, due_date
                """)

                result = db.execute(query, task_params).fetchone()

                if not result:
                    return ToolResult(success=False, error=f"Task {item_id} not found")

                db.commit()

                self.audit_log(
                    "reschedule_task",
                    entity_type="task",
                    entity_id=item_id,
                    details={"new_date": new_date, "reason": reason}
                )

                return ToolResult(
                    success=True,
                    data={
                        "item_type": "task",
                        "item_id": result.id,
                        "title": result.title,
                        "new_date": result.due_date.isoformat() if result.due_date else None
                    },
                    message=f"Task '{result.title}' rescheduled to {new_date}"
                )

            elif item_type == "appointment":
                # Get current appointment for duration
                appt_params = {"item_id": item_id}
                if org_id:
                    appt_params["org_id"] = org_id
                current = db.execute(
                    text(f"SELECT start_time, end_time FROM appointments WHERE id = :item_id {org_clause}"),
                    appt_params
                ).fetchone()

                if not current:
                    return ToolResult(success=False, error=f"Appointment {item_id} not found")

                # Calculate new times
                if new_time:
                    new_start = datetime.fromisoformat(f"{new_date}T{new_time}:00")
                else:
                    old_time = current.start_time.time() if current.start_time else datetime.now().time()
                    new_start = datetime.fromisoformat(f"{new_date}T{old_time.isoformat()}")

                if current.start_time and current.end_time:
                    duration = current.end_time - current.start_time
                    new_end = new_start + duration
                else:
                    new_end = new_start + timedelta(minutes=30)

                appt_update_params = {
                    "item_id": item_id,
                    "new_start": new_start,
                    "new_end": new_end,
                    "reschedule_note": f"\n[{datetime.now().isoformat()}] Rescheduled: {reason}"
                }
                if org_id:
                    appt_update_params["org_id"] = org_id

                query = text(f"""
                    UPDATE appointments
                    SET start_time = :new_start,
                        end_time = :new_end,
                        notes = COALESCE(notes, '') || :reschedule_note,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :item_id {org_clause}
                    RETURNING id, title, start_time, end_time
                """)

                result = db.execute(query, appt_update_params).fetchone()

                db.commit()

                self.audit_log(
                    "reschedule_appointment",
                    entity_type="appointment",
                    entity_id=item_id,
                    details={"new_start": new_start.isoformat(), "reason": reason}
                )

                return ToolResult(
                    success=True,
                    data={
                        "item_type": "appointment",
                        "item_id": result.id,
                        "title": result.title,
                        "new_start": result.start_time.isoformat(),
                        "new_end": result.end_time.isoformat() if result.end_time else None
                    },
                    message=f"Appointment '{result.title}' rescheduled to {result.start_time.strftime('%m/%d/%Y %I:%M %p')}"
                )

            else:
                return ToolResult(success=False, error=f"Invalid item type: {item_type}")

        except Exception as e:
            db.rollback()
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()

    async def _get_overdue(
        self,
        input_data: Dict[str, Any],
        context: AgentContext
    ) -> ToolResult:
        """Get all overdue items"""
        from database import SessionLocal

        db = SessionLocal()
        try:
            org_id = self.context.get("organization_id")
            limit = input_data.get("limit", 50)
            user_id = input_data.get("user_id")
            entity_type = input_data.get("entity_type")

            params = {"limit": limit}
            conditions = ["due_date < CURRENT_DATE", "status NOT IN ('completed', 'cancelled')"]

            if org_id:
                conditions.append("organization_id = :org_id")
                params["org_id"] = org_id

            if user_id:
                conditions.append("assigned_to = :user_id")
                params["user_id"] = user_id

            if entity_type:
                conditions.append("entity_type = :entity_type")
                params["entity_type"] = entity_type

            where_clause = " AND ".join(conditions)

            query = text(f"""
                SELECT
                    id, title, description, priority, task_type,
                    due_date, entity_type, entity_id,
                    EXTRACT(DAY FROM CURRENT_DATE - due_date) as days_overdue
                FROM tasks
                WHERE {where_clause}
                ORDER BY due_date ASC
                LIMIT :limit
            """)

            results = db.execute(query, params).fetchall()

            overdue_items = []
            critical_count = 0
            for r in results:
                days = int(r.days_overdue or 0)
                if days > 7:
                    critical_count += 1
                overdue_items.append({
                    "id": r.id,
                    "title": r.title,
                    "priority": r.priority,
                    "task_type": r.task_type,
                    "due_date": r.due_date.isoformat() if r.due_date else None,
                    "days_overdue": days,
                    "severity": "critical" if days > 7 else "warning" if days > 3 else "minor",
                    "entity_type": r.entity_type,
                    "entity_id": r.entity_id
                })

            return ToolResult(
                success=True,
                data={
                    "overdue_items": overdue_items,
                    "count": len(overdue_items),
                    "critical_count": critical_count,
                    "summary": {
                        "1-3_days": sum(1 for i in overdue_items if i["days_overdue"] <= 3),
                        "4-7_days": sum(1 for i in overdue_items if 3 < i["days_overdue"] <= 7),
                        "7+_days": critical_count
                    }
                },
                message=f"Found {len(overdue_items)} overdue items, {critical_count} critical (7+ days)"
            )

        except Exception as e:
            return ToolResult(success=False, error=str(e))
        finally:
            db.close()
