"""Task tools — read and create (extracted verbatim)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Callable, Dict

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def build_task_tools(db: Session, current_user: Any, ctx: Dict[str, Any]) -> Dict[str, Callable]:
    tools: Dict[str, Callable] = {}

    org_id = ctx["org_id"]

    # ============ Task Tools ============

    async def execute_get_tasks(args):
        """Get user's tasks for a specific timeframe."""
        timeframe = args.get("timeframe", "today")
        today = datetime.now().date()

        # Query ai_tasks table (the active task table) instead of tasks
        task_query = text("""
            SELECT t.id, t.title, t.due_date, t.type as status, t.priority, t.description,
                   COALESCE(t.borrower_name, ln.borrower_name, ld.name) as borrower_name,
                   ln.amount as loan_amount, ln.stage as loan_stage, ln.loan_number,
                   t.loan_id, t.lead_id
            FROM ai_tasks t
            LEFT JOIN loans ln ON t.loan_id = ln.id
            LEFT JOIN leads ld ON t.lead_id = ld.id
            WHERE t.assigned_to_id = :user_id AND t.type::text != 'Completed'
            AND (:org_id IS NULL OR t.organization_id = :org_id)
            ORDER BY
                CASE WHEN t.priority = 'high' THEN 1 WHEN t.priority = 'medium' THEN 2 ELSE 3 END,
                t.due_date ASC NULLS LAST
        """)

        result = db.execute(task_query, {"user_id": current_user.id, "org_id": org_id})
        all_tasks = result.fetchall()

        filtered_tasks = []
        for row in all_tasks:
            task_date = row[2].date() if row[2] else None
            include = False

            if timeframe == "today":
                include = task_date == today
            elif timeframe == "tomorrow":
                include = task_date == today + timedelta(days=1)
            elif timeframe == "this_week":
                include = task_date and today <= task_date <= today + timedelta(days=7)
            elif timeframe == "overdue":
                include = task_date and task_date < today
            else:
                include = True

            if include:
                filtered_tasks.append(row)

        return {
            "count": len(filtered_tasks),
            "timeframe": timeframe,
            "tasks": [{
                "id": r[0],
                "title": r[1],
                "due_date": r[2].isoformat() if r[2] else None,
                "status": r[3],
                "priority": r[4],
                "description": r[5][:100] if r[5] else None,
                "borrower_name": r[6],
                "loan_amount": float(r[7]) if r[7] else None,
                "loan_stage": r[8],
                "loan_number": r[9]
            } for r in filtered_tasks[:15]]
        }

    tools["get_tasks"] = execute_get_tasks

    # ============ Task Creation Tools ============

    async def execute_create_task(args):
        """Create a new task for the user."""
        title = args.get("title", "New Task")
        description = args.get("description", "")
        due_date = args.get("due_date")
        priority = args.get("priority", "medium")
        loan_id = args.get("loan_id")
        lead_id = args.get("lead_id")

        try:
            # Parse due_date if provided
            due_datetime = None
            if due_date:
                try:
                    due_datetime = datetime.fromisoformat(due_date.replace('Z', '+00:00'))
                except Exception as e:
                    logger.error(f"Error parsing due_date: {e}")
                    due_datetime = datetime.now() + timedelta(days=1)

            # Insert into ai_tasks table (the active task table)
            result = db.execute(
                text("""INSERT INTO ai_tasks (title, description, due_date, priority, type,
                       assigned_to_id, loan_id, lead_id, organization_id, created_at, updated_at)
                       VALUES (:title, :description, :due_date, :priority, 'In Progress',
                       :assigned_to_id, :loan_id, :lead_id, :org_id, NOW(), NOW())
                       RETURNING id, title"""),
                {
                    "title": title,
                    "description": description,
                    "due_date": due_datetime,
                    "priority": priority,
                    "assigned_to_id": current_user.id,
                    "loan_id": loan_id,
                    "lead_id": lead_id,
                    "org_id": org_id,
                }
            )
            db.commit()
            row = result.fetchone()

            # Invalidate task-related caches for this user
            try:
                from core.cache import invalidate_user_cache
                await invalidate_user_cache(str(current_user.id))
            except Exception as cache_e:
                logger.debug(f"Cache invalidation skipped: {cache_e}")

            return {
                "success": True,
                "task_id": row.id,
                "title": row.title,
                "message": f"Task '{title}' created successfully"
            }
        except Exception as e:
            logger.error(f"Error in create_task: {e}")
            db.rollback()
            return {"success": False, "error": "Internal server error"}

    tools["create_task"] = execute_create_task

    return tools
