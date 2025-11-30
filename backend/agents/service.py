"""
AI Agent Service

This service provides the interface between FastAPI endpoints and the
LangGraph orchestrator. It handles session management, tool registration,
and response formatting.
"""

import asyncio
import logging
import os
from typing import Any, Callable, Dict, Optional
from datetime import datetime

from anthropic import Anthropic
from sqlalchemy.orm import Session

from .orchestrator import run_orchestrator, OrchestratorSession

logger = logging.getLogger(__name__)


class AIAgentService:
    """
    Service class for the LangGraph AI Agent.

    This class provides methods to run the agent from FastAPI endpoints,
    managing the integration with the database session and user context.
    """

    def __init__(
        self,
        db: Session,
        current_user: Any,
        autonomous_mode: bool = True
    ):
        """
        Initialize the AI Agent Service.

        Args:
            db: SQLAlchemy database session
            current_user: Authenticated user object
            autonomous_mode: Whether to auto-execute low-risk actions
        """
        self.db = db
        self.current_user = current_user
        self.autonomous_mode = autonomous_mode

        # Initialize Anthropic client
        self.anthropic_client = Anthropic(
            api_key=os.getenv("ANTHROPIC_API_KEY")
        )

        # Tool functions will be registered when processing
        self._tool_functions: Dict[str, Callable] = {}

    def register_tool(self, name: str, func: Callable):
        """Register a tool function that the agent can use."""
        self._tool_functions[name] = func

    def register_tools(self, tools: Dict[str, Callable]):
        """Register multiple tool functions."""
        self._tool_functions.update(tools)

    async def process_message(
        self,
        message: str,
        conversation_history: Optional[list] = None,
        return_structured: bool = False
    ) -> Dict[str, Any]:
        """
        Process a user message through the LangGraph orchestrator.

        Args:
            message: User's input message
            conversation_history: Previous messages in the conversation
            return_structured: Whether to return structured response data

        Returns:
            Response dictionary with text and metadata
        """
        try:
            # Run the orchestrator
            result = await run_orchestrator(
                message=message,
                user_id=str(self.current_user.id),
                user_email=self.current_user.email,
                user_role=getattr(self.current_user, 'role', 'loan_officer'),
                tool_functions=self._tool_functions,
                anthropic_client=self.anthropic_client,
                autonomous_mode=self.autonomous_mode,
                conversation_history=conversation_history,
                return_structured=return_structured
            )

            # Log the interaction
            await self._log_interaction(message, result)

            return result

        except Exception as e:
            logger.error(f"AI Agent processing failed: {e}", exc_info=True)
            return {
                "response": "I apologize, but I encountered an error. Please try again.",
                "error": str(e)
            }

    async def process_message_stream(
        self,
        message: str,
        conversation_history: Optional[list] = None
    ):
        """
        Process a user message and stream the response.

        This is a placeholder for streaming implementation.
        Currently returns the full response in one chunk.

        Args:
            message: User's input message
            conversation_history: Previous messages

        Yields:
            Response chunks as they become available
        """
        # For now, just yield the full response
        # TODO: Implement true streaming with LangGraph callbacks
        result = await self.process_message(message, conversation_history)
        yield result

    async def _log_interaction(self, message: str, result: Dict[str, Any]):
        """Log the AI interaction for analytics and debugging."""
        try:
            # Import here to avoid circular imports
            from sqlalchemy import text

            log_query = text("""
                INSERT INTO ai_interactions (
                    user_id, message, response, intent, confidence,
                    processing_time_seconds, created_at
                ) VALUES (
                    :user_id, :message, :response, :intent, :confidence,
                    :processing_time, NOW()
                )
            """)

            self.db.execute(log_query, {
                "user_id": self.current_user.id,
                "message": message[:1000],  # Truncate if too long
                "response": result.get("response", "")[:5000],
                "intent": result.get("intent", "unknown"),
                "confidence": result.get("confidence", 0),
                "processing_time": result.get("processing_time_seconds", 0)
            })
            self.db.commit()

        except Exception as e:
            # Don't fail the request if logging fails
            logger.warning(f"Failed to log AI interaction: {e}")


def create_tool_functions_from_main(db: Session, current_user: Any) -> Dict[str, Callable]:
    """
    Create tool functions that match the existing main.py implementations.

    This function creates async wrappers around the existing tool implementations
    in main.py so they can be used with the LangGraph orchestrator.

    Args:
        db: Database session
        current_user: Current user object

    Returns:
        Dictionary mapping tool names to async functions
    """
    from sqlalchemy import text
    from datetime import datetime, timedelta

    tools = {}

    # ============ Pipeline Tools ============

    async def execute_get_pipeline(args):
        """Get pipeline summary with leads and loans by stage."""
        include_details = args.get("include_details", True)

        try:
            # Get leads using raw SQL to avoid import issues
            lead_rows = db.execute(
                text("""SELECT id, name, email, phone, stage
                       FROM leads WHERE owner_id = :user_id"""),
                {"user_id": current_user.id}
            ).fetchall()

            # Get loans using raw SQL
            loan_rows = db.execute(
                text("""SELECT id, loan_number, borrower_name, stage, amount,
                       processor, underwriter, days_in_stage, closing_date
                       FROM loans WHERE loan_officer_id = :user_id"""),
                {"user_id": current_user.id}
            ).fetchall()

            # Organize leads by stage
            lead_stages = {}
            for lead in lead_rows:
                stage = str(lead.stage) if lead.stage else "New"
                if stage not in lead_stages:
                    lead_stages[stage] = {"count": 0, "items": []}
                lead_stages[stage]["count"] += 1
                if include_details:
                    lead_stages[stage]["items"].append({
                        "id": lead.id,
                        "name": lead.name,
                        "type": "lead"
                    })

            # Organize loans by stage
            loan_stages = {}
            for loan in loan_rows:
                stage = str(loan.stage) if loan.stage else "Unknown"
                if stage not in loan_stages:
                    loan_stages[stage] = {"count": 0, "items": []}
                loan_stages[stage]["count"] += 1
                if include_details:
                    loan_stages[stage]["items"].append({
                        "id": loan.id,
                        "name": loan.borrower_name or f"Loan #{loan.id}",
                        "amount": float(loan.amount) if loan.amount else 0,
                        "processor": loan.processor,
                        "underwriter": loan.underwriter,
                        "days_in_stage": loan.days_in_stage,
                        "closing_date": loan.closing_date.isoformat() if loan.closing_date else None,
                        "type": "loan"
                    })

            return {
                "total_leads": len(lead_rows),
                "total_loans": len(loan_rows),
                "lead_stages": lead_stages,
                "loan_stages": loan_stages,
                "summary": f"{len(lead_rows)} leads, {len(loan_rows)} active loans"
            }
        except Exception as e:
            logger.error(f"Error in get_pipeline: {e}")
            return {"error": str(e), "total_leads": 0, "total_loans": 0}

    tools["get_pipeline"] = execute_get_pipeline

    # ============ Task Tools ============

    async def execute_get_tasks(args):
        """Get user's tasks for a specific timeframe."""
        timeframe = args.get("timeframe", "today")
        today = datetime.now().date()

        task_query = text("""
            SELECT t.id, t.title, t.due_date, t.status, t.priority, t.description,
                   COALESCE(ln.borrower_name, ld.name, t.related_contact_name) as borrower_name,
                   ln.amount as loan_amount, ln.stage as loan_stage, ln.loan_number,
                   t.loan_id, t.lead_id
            FROM tasks t
            LEFT JOIN loans ln ON t.loan_id = ln.id
            LEFT JOIN leads ld ON t.lead_id = ld.id
            WHERE t.owner_id = :user_id AND t.status != 'completed'
            ORDER BY
                CASE WHEN t.priority = 'high' THEN 1 WHEN t.priority = 'medium' THEN 2 ELSE 3 END,
                t.due_date ASC NULLS LAST
        """)

        result = db.execute(task_query, {"user_id": current_user.id})
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

    # ============ Search Tools ============

    async def execute_search_leads(args):
        """Search for leads by name, email, or phone."""
        query_str = args.get("query", "")
        limit = args.get("limit", 10)

        try:
            if query_str:
                search = f"%{query_str}%"
                lead_rows = db.execute(
                    text("""SELECT id, name, email, phone, stage
                           FROM leads
                           WHERE owner_id = :user_id
                           AND (name ILIKE :search OR email ILIKE :search OR phone ILIKE :search)
                           LIMIT :limit"""),
                    {"user_id": current_user.id, "search": search, "limit": limit}
                ).fetchall()
            else:
                lead_rows = db.execute(
                    text("""SELECT id, name, email, phone, stage
                           FROM leads WHERE owner_id = :user_id LIMIT :limit"""),
                    {"user_id": current_user.id, "limit": limit}
                ).fetchall()

            return {
                "count": len(lead_rows),
                "leads": [{
                    "id": l.id,
                    "name": l.name,
                    "email": l.email,
                    "phone": l.phone,
                    "stage": str(l.stage) if l.stage else None
                } for l in lead_rows]
            }
        except Exception as e:
            logger.error(f"Error in search_leads: {e}")
            return {"count": 0, "leads": [], "error": str(e)}

    tools["search_leads"] = execute_search_leads

    # ============ Loan Search Tools ============

    async def execute_search_loans(args):
        """Search for loans by borrower name, loan number, or property address."""
        query_str = args.get("query", "")
        limit = args.get("limit", 10)

        try:
            if query_str:
                search = f"%{query_str}%"
                loan_rows = db.execute(
                    text("""SELECT id, loan_number, borrower_name, stage, amount,
                           processor, underwriter, property_address, closing_date
                           FROM loans
                           WHERE loan_officer_id = :user_id
                           AND (borrower_name ILIKE :search OR loan_number ILIKE :search
                                OR property_address ILIKE :search)
                           LIMIT :limit"""),
                    {"user_id": current_user.id, "search": search, "limit": limit}
                ).fetchall()
            else:
                loan_rows = db.execute(
                    text("""SELECT id, loan_number, borrower_name, stage, amount,
                           processor, underwriter, property_address, closing_date
                           FROM loans WHERE loan_officer_id = :user_id LIMIT :limit"""),
                    {"user_id": current_user.id, "limit": limit}
                ).fetchall()

            return {
                "count": len(loan_rows),
                "loans": [{
                    "id": l.id,
                    "loan_number": l.loan_number,
                    "borrower_name": l.borrower_name,
                    "stage": str(l.stage) if l.stage else None,
                    "amount": float(l.amount) if l.amount else None,
                    "processor": l.processor,
                    "underwriter": l.underwriter,
                    "property_address": l.property_address,
                    "closing_date": l.closing_date.isoformat() if l.closing_date else None
                } for l in loan_rows]
            }
        except Exception as e:
            logger.error(f"Error in search_loans: {e}")
            return {"count": 0, "loans": [], "error": str(e)}

    tools["search_loans"] = execute_search_loans

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
                except:
                    due_datetime = datetime.now() + timedelta(days=1)

            result = db.execute(
                text("""INSERT INTO tasks (title, description, due_date, priority, status,
                       owner_id, loan_id, lead_id, created_at, updated_at)
                       VALUES (:title, :description, :due_date, :priority, 'pending',
                       :owner_id, :loan_id, :lead_id, NOW(), NOW())
                       RETURNING id, title"""),
                {
                    "title": title,
                    "description": description,
                    "due_date": due_datetime,
                    "priority": priority,
                    "owner_id": current_user.id,
                    "loan_id": loan_id,
                    "lead_id": lead_id
                }
            )
            db.commit()
            row = result.fetchone()

            return {
                "success": True,
                "task_id": row.id,
                "title": row.title,
                "message": f"Task '{title}' created successfully"
            }
        except Exception as e:
            logger.error(f"Error in create_task: {e}")
            db.rollback()
            return {"success": False, "error": str(e)}

    tools["create_task"] = execute_create_task

    # ============ Analytics Tools ============

    async def execute_get_pipeline_metrics(args):
        """Get pipeline analytics and metrics."""
        try:
            # Get loan counts by stage
            stage_counts = db.execute(
                text("""SELECT stage, COUNT(*) as count, SUM(amount) as total_amount
                       FROM loans WHERE loan_officer_id = :user_id
                       GROUP BY stage"""),
                {"user_id": current_user.id}
            ).fetchall()

            # Get closing metrics
            closing_metrics = db.execute(
                text("""SELECT
                       COUNT(*) FILTER (WHERE closing_date <= CURRENT_DATE + INTERVAL '7 days') as closing_7_days,
                       COUNT(*) FILTER (WHERE closing_date <= CURRENT_DATE + INTERVAL '30 days') as closing_30_days,
                       SUM(amount) FILTER (WHERE closing_date <= CURRENT_DATE + INTERVAL '30 days') as volume_30_days
                       FROM loans WHERE loan_officer_id = :user_id AND stage != 'closed'"""),
                {"user_id": current_user.id}
            ).fetchone()

            return {
                "stage_breakdown": [{
                    "stage": str(s.stage) if s.stage else "Unknown",
                    "count": s.count,
                    "total_amount": float(s.total_amount) if s.total_amount else 0
                } for s in stage_counts],
                "closing_7_days": closing_metrics.closing_7_days or 0,
                "closing_30_days": closing_metrics.closing_30_days or 0,
                "volume_30_days": float(closing_metrics.volume_30_days) if closing_metrics.volume_30_days else 0
            }
        except Exception as e:
            logger.error(f"Error in get_pipeline_metrics: {e}")
            return {"error": str(e)}

    tools["get_pipeline_metrics"] = execute_get_pipeline_metrics

    # ============ Rate Lock Advisory Tools ============

    async def execute_get_rate_lock_advisory(args):
        """Get rate lock advisory based on market conditions and loan specifics."""
        days_to_close = args.get("days_to_close", 30)

        try:
            # Get loans closing in the specified timeframe
            loans = db.execute(
                text("""SELECT id, loan_number, borrower_name, amount, closing_date,
                       rate, lock_expiration_date
                       FROM loans
                       WHERE loan_officer_id = :user_id
                       AND closing_date <= CURRENT_DATE + INTERVAL ':days days'
                       AND stage NOT IN ('closed', 'denied', 'withdrawn')
                       ORDER BY closing_date ASC""".replace(':days', str(days_to_close))),
                {"user_id": current_user.id}
            ).fetchall()

            # Provide advisory based on general market principles
            advisory = {
                "recommendation": "float" if days_to_close > 45 else "lock",
                "confidence": 0.7,
                "reasoning": "Based on typical market volatility and time to close",
                "loans_affected": len(loans),
                "loans": [{
                    "loan_number": l.loan_number,
                    "borrower_name": l.borrower_name,
                    "amount": float(l.amount) if l.amount else 0,
                    "closing_date": l.closing_date.isoformat() if l.closing_date else None,
                    "current_rate": float(l.rate) if l.rate else None,
                    "lock_status": "locked" if l.lock_expiration_date else "floating"
                } for l in loans[:10]]
            }

            return advisory
        except Exception as e:
            logger.error(f"Error in get_rate_lock_advisory: {e}")
            return {"error": str(e), "recommendation": "consult_manager"}

    tools["get_rate_lock_advisory"] = execute_get_rate_lock_advisory

    # ============ Daily Priorities Tools ============

    async def execute_get_daily_priorities(args):
        """Get prioritized list of actions for today."""
        try:
            # Get overdue tasks
            overdue_tasks = db.execute(
                text("""SELECT id, title, due_date, priority,
                       COALESCE(ln.borrower_name, ld.name) as contact_name
                       FROM tasks t
                       LEFT JOIN loans ln ON t.loan_id = ln.id
                       LEFT JOIN leads ld ON t.lead_id = ld.id
                       WHERE t.owner_id = :user_id
                       AND t.status != 'completed'
                       AND t.due_date < CURRENT_DATE
                       ORDER BY t.priority DESC, t.due_date ASC
                       LIMIT 5"""),
                {"user_id": current_user.id}
            ).fetchall()

            # Get today's tasks
            today_tasks = db.execute(
                text("""SELECT id, title, due_date, priority,
                       COALESCE(ln.borrower_name, ld.name) as contact_name
                       FROM tasks t
                       LEFT JOIN loans ln ON t.loan_id = ln.id
                       LEFT JOIN leads ld ON t.lead_id = ld.id
                       WHERE t.owner_id = :user_id
                       AND t.status != 'completed'
                       AND t.due_date::date = CURRENT_DATE
                       ORDER BY t.priority DESC
                       LIMIT 10"""),
                {"user_id": current_user.id}
            ).fetchall()

            # Get loans closing soon
            closing_soon = db.execute(
                text("""SELECT id, loan_number, borrower_name, closing_date, stage, amount
                       FROM loans
                       WHERE loan_officer_id = :user_id
                       AND closing_date <= CURRENT_DATE + INTERVAL '7 days'
                       AND stage NOT IN ('closed', 'denied', 'withdrawn')
                       ORDER BY closing_date ASC
                       LIMIT 5"""),
                {"user_id": current_user.id}
            ).fetchall()

            return {
                "overdue_tasks": [{
                    "id": t.id,
                    "title": t.title,
                    "due_date": t.due_date.isoformat() if t.due_date else None,
                    "priority": t.priority,
                    "contact_name": t.contact_name
                } for t in overdue_tasks],
                "today_tasks": [{
                    "id": t.id,
                    "title": t.title,
                    "priority": t.priority,
                    "contact_name": t.contact_name
                } for t in today_tasks],
                "closing_soon": [{
                    "loan_number": l.loan_number,
                    "borrower_name": l.borrower_name,
                    "closing_date": l.closing_date.isoformat() if l.closing_date else None,
                    "stage": str(l.stage) if l.stage else None,
                    "amount": float(l.amount) if l.amount else 0
                } for l in closing_soon],
                "summary": f"{len(overdue_tasks)} overdue, {len(today_tasks)} due today, {len(closing_soon)} closing within 7 days"
            }
        except Exception as e:
            logger.error(f"Error in get_daily_priorities: {e}")
            return {"error": str(e)}

    tools["get_daily_priorities"] = execute_get_daily_priorities

    return tools


async def create_ai_agent_service(
    db: Session,
    current_user: Any,
    autonomous_mode: bool = True
) -> AIAgentService:
    """
    Factory function to create a fully configured AI Agent Service.

    This creates the service and registers all available tools.

    Args:
        db: Database session
        current_user: Current user
        autonomous_mode: Whether to auto-execute actions

    Returns:
        Configured AIAgentService instance
    """
    service = AIAgentService(db, current_user, autonomous_mode)

    # Register tools
    tool_functions = create_tool_functions_from_main(db, current_user)
    service.register_tools(tool_functions)

    return service
