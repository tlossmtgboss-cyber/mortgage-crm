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

        # Import Lead model from main.py where it's defined
        try:
            from main import Lead, Loan
        except ImportError:
            logger.warning("Could not import Lead/Loan models")
            return {"error": "Model import failed", "total_leads": 0, "total_loans": 0}

        try:
            # Get leads
            leads = db.query(Lead).filter(Lead.owner_id == current_user.id).all()

            # Get loans using raw SQL
            loan_rows = db.execute(
                text("""SELECT id, loan_number, borrower_name, stage, amount,
                       processor, underwriter, days_in_stage, closing_date
                       FROM loans WHERE loan_officer_id = :user_id"""),
                {"user_id": current_user.id}
            ).fetchall()

            # Organize by stage
            lead_stages = {}
            for lead in leads:
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
                "total_leads": len(leads),
                "total_loans": len(loan_rows),
                "lead_stages": lead_stages,
                "loan_stages": loan_stages,
                "summary": f"{len(leads)} leads, {len(loan_rows)} active loans"
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
        try:
            from main import Lead
        except ImportError:
            logger.warning("Could not import Lead model")
            return {"count": 0, "leads": [], "error": "Model import failed"}

        query_str = args.get("query", "")
        limit = args.get("limit", 10)

        query = db.query(Lead).filter(Lead.owner_id == current_user.id)
        if query_str:
            search = f"%{query_str}%"
            query = query.filter(
                (Lead.name.ilike(search)) |
                (Lead.email.ilike(search)) |
                (Lead.phone.ilike(search))
            )

        leads = query.limit(limit).all()
        return {
            "count": len(leads),
            "leads": [{
                "id": l.id,
                "name": l.name,
                "email": l.email,
                "phone": l.phone,
                "stage": str(l.stage) if l.stage else None
            } for l in leads]
        }

    tools["search_leads"] = execute_search_leads

    # Add more tool implementations as needed...
    # The pattern is the same - wrap existing functionality in async functions

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
