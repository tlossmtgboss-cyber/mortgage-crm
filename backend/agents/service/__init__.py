"""
AI Agent Service (package)

This package provides the interface between FastAPI endpoints and the
LangGraph orchestrator. It handles session management, tool registration,
and response formatting (with streaming support).

Wave 3 decomposition: the original 3,281-line `service.py` monolith has been
split into focused mixins (see `_session.py`, `_tools.py`, `_response.py`,
`_voice.py`) composed by `AIAgentService` via Python's MRO. The public API
(`AIAgentService`, `create_tool_functions_from_main`, `create_ai_agent_service`)
is unchanged — `from agents.service import X` continues to work exactly as
before.
"""

import asyncio
import json
import logging
import os
import uuid
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional
from datetime import datetime, timezone

from anthropic import Anthropic, AsyncAnthropic
from sqlalchemy.orm import Session

from ..anthropic_client import get_anthropic_client, get_async_anthropic_client

from ..orchestrator import run_orchestrator, OrchestratorSession
from ..state import create_initial_state, QueryIntent

# D3: governance hooks — cost / compliance / hallucination guardrails
# Wave 2: helper extracted to service_governance.py; keep flag for back-compat readers.
try:
    from ..orchestration.governance_hooks import run_post_response_governance  # noqa: F401
    _GOVERNANCE_HOOKS_AVAILABLE = True
except Exception as _exc:  # pragma: no cover - never break agent path  # noqa: BLE001
    logger.exception("unhandled exception")
    _GOVERNANCE_HOOKS_AVAILABLE = False
from ..service_governance import apply_post_response_governance

# Import optimized prompt system (local to agents package)
try:
    from ..prompt_integration import OptimizedPromptService
    from ..prompt_loader import LoadContext, ContextPresets, PerenniaContexts
    from ..prompt_router import smart_get_prompt, route_to_optimal_prompt
    PROMPT_OPTIMIZATION_AVAILABLE = True
except ImportError as e:
    import traceback
    traceback.print_exc()
    PROMPT_OPTIMIZATION_AVAILABLE = False

try:
    from utils.pii_mask import mask_phone
except ImportError:
    mask_phone = lambda x: x[:3] + "***" + x[-2:] if x and len(x) > 5 else "***"

logger = logging.getLogger(__name__)


# =============================================================================
# VOICE MODE INSTRUCTIONS — appended to system prompt when voice_mode=True
# =============================================================================
VOICE_MODE_INSTRUCTIONS = """

VOICE MODE — You are Aria, speaking aloud via text-to-speech. You sound like a sharp colleague calling from the next office — warm, quick, human.

RESPONSE FORMAT:
- Maximum 2-3 short sentences per response
- Use natural spoken language, NOT written language
- NO bullet points, numbered lists, markdown, or formatting
- NO asterisks, dashes, or special characters
- Use contractions (I'm, you've, they're, it's, don't, won't)
- Spell out numbers conversationally ("about fifteen hundred" not "1,500", "three loans" not "3 loans")
- Spell out abbreviations ("FHA" say "F-H-A", "LTV" say "L-T-V")

CONVERSATIONAL & EMPATHETIC TONE:
- Speak like a trusted colleague who genuinely cares, not a report generator
- Use natural transitions ("So here's the thing...", "Actually, good news...", "Hey, quick heads up...")
- Match the user's energy — if they're stressed, acknowledge it. If they're excited, match it.
- Show you're thinking ahead: "And while you're on with her, you might want to mention the rate lock — it expires Thursday"
- Ask follow-ups naturally: "Want me to handle that?" / "Should I text them too?" / "Anything else before your next call?"
- For greetings, be warm: "Hey! Good morning. What are we tackling?"
- For wins, celebrate briefly: "Nice, that's another one closed. You're on a roll this month."
- For stress, empathize: "Yeah, that's a lot on one day. Let me help you prioritize."
- For errors, be honest and helpful: "Hmm, I'm not finding that. Want me to try searching a different way?"

NEVER DO THESE IN VOICE MODE:
- Never list items with bullets or numbers
- Never say "here are some suggestions" then list them — give your top recommendation directly
- Never include URLs, file paths, or code
- Never use parenthetical asides (like this)
- Never say the word "pipeline" without context — say "your active deals" or "your loans in progress"
- Never sound robotic or transactional — you're a partner, not a tool
"""


def _summarize_tool_result_for_voice(tool_name: str, result: dict) -> str:
    """Condense a tool result into a 1-2 sentence spoken summary for voice mode.

    When voice_mode=True, the full JSON tool result (often 15+ fields) causes the
    LLM to produce verbose responses despite instructions to be concise. This
    function produces a brief natural-language summary that replaces the full result
    in the LLM's context, while the frontend still receives the full result for
    display and debugging.
    """
    if not result or not isinstance(result, dict):
        return str(result) if result else "No results found."

    # --- Error results: surface the message briefly ---
    if result.get("error"):
        err = result["error"]
        if len(str(err)) > 120:
            err = str(err)[:120] + "..."
        return f"That didn't work: {err}"

    # --- Pipeline metrics ---
    if "total_loans" in result or "pipeline" in tool_name:
        total = result.get("total_loans", result.get("count", 0))
        stages = result.get("by_stage", result.get("stages", {}))
        top_stage = max(stages, key=stages.get) if stages else None
        summary = f"{total} loans in your pipeline."
        if top_stage:
            summary += f" Most are in {top_stage.lower().replace('_', ' ')}."
        return summary

    # --- Lead / loan / generic search results ---
    items_key = None
    for key in ("leads", "loans", "results"):
        if isinstance(result.get(key), list):
            items_key = key
            break

    if items_key is not None:
        items = result[items_key]
        count = result.get("count", result.get("total", len(items)))
        entity = items_key
        if count == 0:
            return f"No {entity} found matching that."
        if count == 1:
            item = items[0]
            name = item.get("borrower_name", item.get("name", item.get("first_name", "Unknown")))
            return f"Found one: {name}."
        # Summarize top 2-3 names
        names = [
            i.get("borrower_name", i.get("name", i.get("first_name", "")))
            for i in items[:3]
        ]
        names_str = ", ".join(n for n in names if n)
        more = f" and {count - 3} more" if count > 3 else ""
        return f"Found {count} {entity} including {names_str}{more}."

    # --- Task results ---
    if "tasks" in result or "task" in tool_name:
        tasks = result.get("tasks", [])
        if isinstance(tasks, list):
            count = len(tasks)
            overdue = sum(1 for t in tasks if t.get("overdue") or t.get("is_overdue"))
            if count == 0:
                return "No pending tasks."
            summary = f"{count} tasks pending."
            if overdue:
                summary += f" {overdue} overdue."
            return summary

    # --- SMS / notification send results ---
    if result.get("success") and (
        "sms" in tool_name or "notification" in tool_name or "send" in tool_name
    ):
        return "Sent successfully."

    # --- Task creation ---
    if result.get("success") and ("create" in tool_name or "task" in tool_name):
        return "Done, task created."

    # --- Email results ---
    if result.get("success") and "email" in tool_name:
        return "Email sent."

    # --- Rate / market data ---
    if "rate" in tool_name or "advisory" in tool_name:
        advice = result.get("recommendation", result.get("advisory", result.get("message", "")))
        if advice:
            return str(advice)[:200]

    # --- Generic: count / total fields ---
    if "count" in result or "total" in result:
        count = result.get("count", result.get("total"))
        return f"Found {count} results."

    # --- Generic: message field ---
    if "message" in result:
        msg = result["message"]
        return str(msg)[:200]

    # --- Fallback: truncate raw result ---
    summary = str(result)
    if len(summary) > 200:
        summary = summary[:200] + "..."
    return summary



# =============================================================================
# Mixin composition — split from the original monolithic class
# =============================================================================
from ._session import SessionStateMixin
from ._tools import ToolDispatchMixin
from ._response import ResponseGenerationMixin
from ._voice import VoiceFormattingMixin


class AIAgentService(
    SessionStateMixin,
    ToolDispatchMixin,
    ResponseGenerationMixin,
    VoiceFormattingMixin,
):
    """
    Service class for the LangGraph AI Agent.

    This class provides methods to run the agent from FastAPI endpoints,
    managing the integration with the database session and user context.

    Implementation is split across four mixins (composed via Python's MRO):
    SessionStateMixin, ToolDispatchMixin, ResponseGenerationMixin, and
    VoiceFormattingMixin. The constructor and shared instance state live
    here.
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

        # Initialize Anthropic clients (sync and async) with timeout/retry
        self.anthropic_client = get_anthropic_client()
        self.async_anthropic_client = get_async_anthropic_client()

        # Model configuration
        self.model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")

        # Tool functions will be registered when processing
        self._tool_functions: Dict[str, Callable] = {}

        # Tool definitions for API calls
        self._tool_definitions: List[Dict] = []

        # Initialize optimized prompt service (50-80% token reduction)
        self._prompt_service: Optional["OptimizedPromptService"] = None
        if PROMPT_OPTIMIZATION_AVAILABLE:
            try:
                prompts_dir = os.path.join(
                    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
                    'perennia-prompts'
                )
                if os.path.exists(prompts_dir):
                    self._prompt_service = OptimizedPromptService(
                        prompts_dir,
                        cache_ttl_seconds=300,  # 5 minute cache
                        enable_cache=True
                    )
                    # Pre-warm common contexts
                    self._prompt_service.warm_cache()
                    logger.info(f"Optimized prompt service initialized from {prompts_dir}")
            except Exception as e:
                logger.warning(f"Could not initialize optimized prompts: {e}")


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

    # Defense-in-depth: Extract org_id for tenant isolation (AI-004/AI-007)
    org_id = getattr(current_user, 'organization_id', None)
    if org_id is None:
        logger.warning(
            f"[TOOLS] No organization_id on current_user (id={getattr(current_user, 'id', '?')}) "
            "— tenant isolation degraded for AI tool queries"
        )

    # Determine data scope: admins/managers see org-wide, others see own data only
    _user_role = (getattr(current_user, 'permission_role', '') or '').lower()
    _has_org_wide_access = _user_role in ('admin', 'site_admin', 'leadership', 'management')
    if _has_org_wide_access:
        logger.info(f"[TOOLS] User {getattr(current_user, 'id', '?')} has org-wide AI tool access (role={_user_role})")

    # ============ Pipeline Tools ============

    async def execute_get_pipeline(args):
        """Get pipeline summary with leads and loans by stage."""
        include_details = args.get("include_details", True)

        try:
            # Scope: org-wide for admins/managers, user-only for others
            if _has_org_wide_access and org_id:
                lead_filter = "organization_id = :org_id"
                loan_filter = "organization_id = :org_id"
                params = {"org_id": org_id}
            elif _has_org_wide_access and not org_id:
                # Platform admin with no org — show all
                lead_filter = "1=1"
                loan_filter = "1=1"
                params = {}
            else:
                lead_filter = "owner_id = :user_id AND (:org_id IS NULL OR organization_id = :org_id)"
                loan_filter = "loan_officer_id = :user_id AND (:org_id IS NULL OR organization_id = :org_id)"
                params = {"user_id": current_user.id, "org_id": org_id}

            # Get leads using raw SQL to avoid import issues (include owner for org-wide views)
            lead_where = lead_filter.replace('organization_id', 'ld.organization_id').replace('owner_id', 'ld.owner_id')
            lead_sql = (
                "SELECT ld.id, ld.name, ld.email, ld.phone, ld.stage,"
                " CONCAT(u.first_name, ' ', u.last_name) as owner_name"
                " FROM leads ld"
                " LEFT JOIN users u ON u.id = ld.owner_id"
                " WHERE " + lead_where
            )
            lead_rows = db.execute(
                text(lead_sql),
                params
            ).fetchall()

            # Get loans using raw SQL (include LO name for org-wide views)
            loan_where = loan_filter.replace('organization_id', 'l.organization_id').replace('loan_officer_id', 'l.loan_officer_id')
            loan_sql = (
                "SELECT l.id, l.loan_number, l.borrower_name, l.stage, l.amount,"
                " l.processor, l.underwriter, l.days_in_stage, l.closing_date,"
                " CONCAT(u.first_name, ' ', u.last_name) as lo_name"
                " FROM loans l"
                " LEFT JOIN users u ON u.id = l.loan_officer_id"
                " WHERE " + loan_where
            )
            loan_rows = db.execute(
                text(loan_sql),
                params
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
                    item = {
                        "id": loan.id,
                        "name": loan.borrower_name or f"Loan #{loan.id}",
                        "amount": float(loan.amount) if loan.amount else 0,
                        "processor": loan.processor,
                        "underwriter": loan.underwriter,
                        "days_in_stage": loan.days_in_stage,
                        "closing_date": loan.closing_date.isoformat() if loan.closing_date else None,
                        "type": "loan"
                    }
                    lo_name = getattr(loan, 'lo_name', None)
                    if lo_name and _has_org_wide_access:
                        item["loan_officer"] = lo_name
                    loan_stages[stage]["items"].append(item)

            scope_label = "organization-wide" if _has_org_wide_access else "your"
            return {
                "total_leads": len(lead_rows),
                "total_loans": len(loan_rows),
                "lead_stages": lead_stages,
                "loan_stages": loan_stages,
                "scope": "organization" if _has_org_wide_access else "user",
                "summary": f"{len(lead_rows)} leads, {len(loan_rows)} active loans ({scope_label})"
            }
        except Exception as e:
            logger.error(f"Error in get_pipeline: {e}")
            db.rollback()
            return {"error": "Internal server error", "total_leads": 0, "total_loans": 0}

    tools["get_pipeline"] = execute_get_pipeline

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

    # ============ Search Tools ============

    async def execute_search_leads(args):
        """Search for leads by name, email, or phone."""
        query_str = args.get("query", "")
        limit = args.get("limit", 10)

        try:
            # Scope: org-wide for admins/managers, user-only for others
            if _has_org_wide_access and org_id:
                base_filter = "organization_id = :org_id"
                base_params = {"org_id": org_id, "limit": limit}
            elif _has_org_wide_access and not org_id:
                base_filter = "1=1"
                base_params = {"limit": limit}
            else:
                base_filter = "owner_id = :user_id AND (:org_id IS NULL OR organization_id = :org_id)"
                base_params = {"user_id": current_user.id, "org_id": org_id, "limit": limit}

            if query_str:
                search = f"%{query_str}%"
                base_params["search"] = search
                lead_search_sql = (
                    "SELECT id, name, email, phone, stage"
                    " FROM leads"
                    " WHERE " + base_filter +
                    " AND (name ILIKE :search OR email ILIKE :search OR phone ILIKE :search)"
                    " LIMIT :limit"
                )
                lead_rows = db.execute(
                    text(lead_search_sql),
                    base_params
                ).fetchall()
            else:
                lead_list_sql = (
                    "SELECT id, name, email, phone, stage"
                    " FROM leads WHERE " + base_filter +
                    " LIMIT :limit"
                )
                lead_rows = db.execute(
                    text(lead_list_sql),
                    base_params
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
            db.rollback()
            return {"count": 0, "leads": [], "error": "Internal server error"}

    tools["search_leads"] = execute_search_leads

    # ============ Loan Search Tools ============

    async def execute_search_loans(args):
        """Search for loans by borrower name, loan number, or property address."""
        query_str = args.get("query", "")
        limit = args.get("limit", 10)

        try:
            # Scope: org-wide for admins/managers, user-only for others
            if _has_org_wide_access and org_id:
                base_filter = "organization_id = :org_id"
                base_params = {"org_id": org_id, "limit": limit}
            elif _has_org_wide_access and not org_id:
                base_filter = "1=1"
                base_params = {"limit": limit}
            else:
                base_filter = "loan_officer_id = :user_id AND (:org_id IS NULL OR organization_id = :org_id)"
                base_params = {"user_id": current_user.id, "org_id": org_id, "limit": limit}

            if query_str:
                search = f"%{query_str}%"
                base_params["search"] = search
                loan_search_sql = (
                    "SELECT id, loan_number, borrower_name, stage, amount,"
                    " processor, underwriter, property_address, closing_date"
                    " FROM loans"
                    " WHERE " + base_filter +
                    " AND (borrower_name ILIKE :search OR loan_number ILIKE :search"
                    " OR property_address ILIKE :search)"
                    " LIMIT :limit"
                )
                loan_rows = db.execute(
                    text(loan_search_sql),
                    base_params
                ).fetchall()
            else:
                loan_list_sql = (
                    "SELECT id, loan_number, borrower_name, stage, amount,"
                    " processor, underwriter, property_address, closing_date"
                    " FROM loans WHERE " + base_filter +
                    " LIMIT :limit"
                )
                loan_rows = db.execute(
                    text(loan_list_sql),
                    base_params
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
            db.rollback()
            return {"count": 0, "loans": [], "error": "Internal server error"}

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

    # ============ Analytics Tools ============

    async def execute_get_pipeline_metrics(args):
        """Get pipeline analytics and metrics."""
        try:
            # Get loan counts by stage
            stage_counts = db.execute(
                text("""SELECT stage, COUNT(*) as count, SUM(amount) as total_amount
                       FROM loans WHERE loan_officer_id = :user_id
                       AND (:org_id IS NULL OR organization_id = :org_id)
                       GROUP BY stage"""),
                {"user_id": current_user.id, "org_id": org_id}
            ).fetchall()

            # Get closing metrics (only count future closing dates)
            closing_metrics = db.execute(
                text("""SELECT
                       COUNT(*) FILTER (WHERE closing_date >= CURRENT_DATE AND closing_date <= CURRENT_DATE + INTERVAL '7 days') as closing_7_days,
                       COUNT(*) FILTER (WHERE closing_date >= CURRENT_DATE AND closing_date <= CURRENT_DATE + INTERVAL '30 days') as closing_30_days,
                       SUM(amount) FILTER (WHERE closing_date >= CURRENT_DATE AND closing_date <= CURRENT_DATE + INTERVAL '30 days') as volume_30_days
                       FROM loans WHERE loan_officer_id = :user_id AND stage::text != 'Funded'
                       AND (:org_id IS NULL OR organization_id = :org_id)"""),
                {"user_id": current_user.id, "org_id": org_id}
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
            db.rollback()
            return {"error": "Internal server error"}

    tools["get_pipeline_metrics"] = execute_get_pipeline_metrics

    # ============ Rate Lock Advisory Tools ============

    async def execute_get_rate_lock_advisory(args):
        """Get rate lock advisory based on market conditions and loan specifics."""
        days_to_close = args.get("days_to_close", 30)

        try:
            # Get loans closing in the specified timeframe (LoanStage enum values use title case like 'Funded')
            # Filter to only include future closing dates
            loans = db.execute(
                text("""SELECT id, loan_number, borrower_name, amount, closing_date,
                       rate, lock_expiration_date
                       FROM loans
                       WHERE loan_officer_id = :user_id
                       AND (:org_id IS NULL OR organization_id = :org_id)
                       AND closing_date >= CURRENT_DATE
                       AND closing_date <= CURRENT_DATE + INTERVAL ':days days'
                       AND stage::text NOT IN ('Funded')
                       ORDER BY closing_date ASC""".replace(':days', str(days_to_close))),
                {"user_id": current_user.id, "org_id": org_id}
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
            db.rollback()
            return {"error": "Internal server error", "recommendation": "consult_manager"}

    tools["get_rate_lock_advisory"] = execute_get_rate_lock_advisory

    # ============ Daily Priorities Tools ============

    async def execute_get_daily_priorities(args):
        """Get prioritized list of actions for today."""
        try:
            # Get overdue tasks from ai_tasks table (the active task table)
            overdue_tasks = db.execute(
                text("""SELECT t.id, t.title, t.due_date, t.priority,
                       COALESCE(t.borrower_name, ln.borrower_name, ld.name) as contact_name
                       FROM ai_tasks t
                       LEFT JOIN loans ln ON t.loan_id = ln.id
                       LEFT JOIN leads ld ON t.lead_id = ld.id
                       WHERE t.assigned_to_id = :user_id
                       AND (:org_id IS NULL OR t.organization_id = :org_id)
                       AND t.type::text != 'Completed'
                       AND t.due_date < CURRENT_DATE
                       ORDER BY
                           CASE WHEN t.priority = 'high' THEN 1
                                WHEN t.priority = 'medium' THEN 2
                                ELSE 3 END,
                           t.due_date ASC
                       LIMIT 5"""),
                {"user_id": current_user.id, "org_id": org_id}
            ).fetchall()

            # Get today's tasks
            today_tasks = db.execute(
                text("""SELECT t.id, t.title, t.due_date, t.priority,
                       COALESCE(t.borrower_name, ln.borrower_name, ld.name) as contact_name
                       FROM ai_tasks t
                       LEFT JOIN loans ln ON t.loan_id = ln.id
                       LEFT JOIN leads ld ON t.lead_id = ld.id
                       WHERE t.assigned_to_id = :user_id
                       AND (:org_id IS NULL OR t.organization_id = :org_id)
                       AND t.type::text != 'Completed'
                       AND t.due_date::date = CURRENT_DATE
                       ORDER BY
                           CASE WHEN t.priority = 'high' THEN 1
                                WHEN t.priority = 'medium' THEN 2
                                ELSE 3 END
                       LIMIT 10"""),
                {"user_id": current_user.id, "org_id": org_id}
            ).fetchall()

            # Also get tomorrow's tasks
            tomorrow_tasks = db.execute(
                text("""SELECT t.id, t.title, t.due_date, t.priority,
                       COALESCE(t.borrower_name, ln.borrower_name, ld.name) as contact_name
                       FROM ai_tasks t
                       LEFT JOIN loans ln ON t.loan_id = ln.id
                       LEFT JOIN leads ld ON t.lead_id = ld.id
                       WHERE t.assigned_to_id = :user_id
                       AND (:org_id IS NULL OR t.organization_id = :org_id)
                       AND t.type::text != 'Completed'
                       AND t.due_date::date = CURRENT_DATE + INTERVAL '1 day'
                       ORDER BY
                           CASE WHEN t.priority = 'high' THEN 1
                                WHEN t.priority = 'medium' THEN 2
                                ELSE 3 END
                       LIMIT 5"""),
                {"user_id": current_user.id, "org_id": org_id}
            ).fetchall()

            # Get loans closing soon (future only - past dates mean loan is delayed or already closed)
            closing_soon = db.execute(
                text("""SELECT id, loan_number, borrower_name, closing_date, stage, amount
                       FROM loans
                       WHERE loan_officer_id = :user_id
                       AND (:org_id IS NULL OR organization_id = :org_id)
                       AND closing_date >= CURRENT_DATE
                       AND closing_date <= CURRENT_DATE + INTERVAL '7 days'
                       AND stage::text NOT IN ('Funded')
                       ORDER BY closing_date ASC
                       LIMIT 5"""),
                {"user_id": current_user.id, "org_id": org_id}
            ).fetchall()

            # Also check for loans with PAST closing dates that aren't funded (these need attention)
            overdue_closings = db.execute(
                text("""SELECT id, loan_number, borrower_name, closing_date, stage, amount
                       FROM loans
                       WHERE loan_officer_id = :user_id
                       AND (:org_id IS NULL OR organization_id = :org_id)
                       AND closing_date < CURRENT_DATE
                       AND stage::text NOT IN ('Funded', 'Cancelled', 'Denied')
                       ORDER BY closing_date DESC
                       LIMIT 5"""),
                {"user_id": current_user.id, "org_id": org_id}
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
                    "due_date": t.due_date.isoformat() if t.due_date else None,
                    "priority": t.priority,
                    "contact_name": t.contact_name
                } for t in today_tasks],
                "tomorrow_tasks": [{
                    "id": t.id,
                    "title": t.title,
                    "due_date": t.due_date.isoformat() if t.due_date else None,
                    "priority": t.priority,
                    "contact_name": t.contact_name
                } for t in tomorrow_tasks],
                "closing_soon": [{
                    "loan_number": l.loan_number,
                    "borrower_name": l.borrower_name,
                    "closing_date": l.closing_date.isoformat() if l.closing_date else None,
                    "stage": str(l.stage) if l.stage else None,
                    "amount": float(l.amount) if l.amount else 0
                } for l in closing_soon],
                "overdue_closings": [{
                    "loan_number": l.loan_number,
                    "borrower_name": l.borrower_name,
                    "closing_date": l.closing_date.isoformat() if l.closing_date else None,
                    "stage": str(l.stage) if l.stage else None,
                    "amount": float(l.amount) if l.amount else 0,
                    "status": "PAST DUE - needs update"
                } for l in overdue_closings],
                "summary": f"{len(overdue_tasks)} overdue tasks, {len(today_tasks)} due today, {len(closing_soon)} closing within 7 days" + (f", {len(overdue_closings)} loans with PAST closing dates needing attention" if overdue_closings else "")
            }
        except Exception as e:
            logger.error(f"Error in get_daily_priorities: {e}")
            db.rollback()  # Roll back to allow subsequent queries
            return {"error": "Internal server error"}

    tools["get_daily_priorities"] = execute_get_daily_priorities

    # ============ Lead Pipeline Intelligence Tools ============

    async def execute_lead_status_insights(args):
        """
        Get lead pipeline intelligence and coaching insights.

        Analyzes leads by status and returns:
        - Summary metrics (counts, conversion rates)
        - Per-status breakdowns with SLA tracking
        - Bottleneck detection
        - Prioritized focus areas with playbooks
        - Trend data over time

        Use this for coaching-level answers, not raw lead lists.
        """
        try:
            from services.lead_status_insights_service import get_lead_status_insights

            # Use current user's ID if not specified
            assigned_to = args.get("assigned_to_user_id")
            if assigned_to is None:
                assigned_to = str(current_user.id)

            insights = get_lead_status_insights(
                db=db,
                assigned_to_user_id=assigned_to,
                include_statuses=args.get("include_statuses"),
                created_date_from=args.get("created_date_from"),
                created_date_to=args.get("created_date_to"),
                time_bucket=args.get("time_bucket", "week")
            )

            return insights
        except Exception as e:
            logger.error(f"Error in lead_status_insights: {e}")
            return {"error": "Internal server error"}

    tools["lead_status_insights"] = execute_lead_status_insights

    async def execute_get_leads_by_status(args):
        """
        Get detailed lead list for specific statuses.

        Use this when you need record-level detail to decide who to call, text, or email.
        For coaching/analytics overview, use lead_status_insights instead.
        """
        statuses = args.get("statuses", ["new", "attempted_contact", "prospect"])
        max_results = args.get("max_results", 100)
        include_details = args.get("include_details", True)

        try:
            # Map status keys to enum values
            status_map = {
                "new": "New",
                "attempted_contact": "Attempted Contact",
                "prospect": "Prospect",
                "application": "Application",
                "pre_qualified": "Pre-Qualified",
                "pre_approved": "Pre-Approved",
                "nurture": "Long-Term Nurture",
                "withdrawn": "Withdrawn",
                "does_not_qualify": "Does Not Qualify"
            }

            mapped_statuses = []
            for s in statuses:
                mapped = status_map.get(s.lower().replace(" ", "_").replace("-", "_"))
                if mapped:
                    mapped_statuses.append(mapped)

            if not mapped_statuses:
                mapped_statuses = ["New", "Attempted Contact", "Prospect"]

            # Build the IN clause safely
            status_placeholders = ", ".join([f":status_{i}" for i in range(len(mapped_statuses))])
            params = {"user_id": current_user.id, "org_id": org_id, "limit": max_results}
            for i, status in enumerate(mapped_statuses):
                params[f"status_{i}"] = status

            leads_by_status_sql = (
                "SELECT id, name, first_name, last_name, email, phone, stage,"
                " source, ai_score, loan_amount, preapproval_amount,"
                " last_contact, created_at, updated_at, notes"
                " FROM leads"
                " WHERE owner_id = :user_id"
                " AND (:org_id IS NULL OR organization_id = :org_id)"
                " AND stage::text IN (" + status_placeholders + ")"
                " ORDER BY"
                " CASE stage::text"
                " WHEN 'New' THEN 1"
                " WHEN 'Attempted Contact' THEN 2"
                " WHEN 'Prospect' THEN 3"
                " WHEN 'Application' THEN 4"
                " WHEN 'Pre-Qualified' THEN 5"
                " WHEN 'Pre-Approved' THEN 6"
                " ELSE 7"
                " END,"
                " updated_at DESC"
                " LIMIT :limit"
            )
            query = text(leads_by_status_sql)

            lead_rows = db.execute(query, params).fetchall()

            leads = []
            for l in lead_rows:
                lead_data = {
                    "id": l.id,
                    "name": l.name,
                    "email": l.email,
                    "phone": l.phone,
                    "stage": str(l.stage) if l.stage else None
                }

                if include_details:
                    lead_data.update({
                        "first_name": l.first_name,
                        "last_name": l.last_name,
                        "source": l.source,
                        "ai_score": l.ai_score,
                        "loan_amount": float(l.loan_amount) if l.loan_amount else None,
                        "preapproval_amount": float(l.preapproval_amount) if l.preapproval_amount else None,
                        "last_contact": l.last_contact.isoformat() if l.last_contact else None,
                        "created_at": l.created_at.isoformat() if l.created_at else None,
                        "updated_at": l.updated_at.isoformat() if l.updated_at else None,
                        "notes": l.notes[:200] if l.notes else None
                    })

                    # Calculate days in current status
                    if l.updated_at:
                        from datetime import datetime, timezone
                        now = datetime.now(timezone.utc)
                        updated = l.updated_at
                        if updated.tzinfo is None:
                            updated = updated.replace(tzinfo=timezone.utc)
                        lead_data["days_in_current_status"] = (now - updated).days

                leads.append(lead_data)

            # Group by status for easy consumption
            by_status = {}
            for lead in leads:
                status = lead.get("stage", "Unknown")
                if status not in by_status:
                    by_status[status] = []
                by_status[status].append(lead)

            return {
                "total_count": len(leads),
                "statuses_queried": mapped_statuses,
                "leads": leads,
                "by_status": by_status
            }
        except Exception as e:
            logger.error(f"Error in get_leads_by_status: {e}")
            db.rollback()
            return {"error": "Internal server error", "leads": []}

    tools["get_leads_by_status"] = execute_get_leads_by_status

    async def execute_get_top_leads(args):
        """
        Get the top leads by score for immediate calling action.

        Returns leads sorted by:
        1. AI score (highest first)
        2. Stage priority (New > Prospect > Application)
        3. Recency (newest first)

        Perfect for "Call my top 3 leads right now" queries.
        All returned leads have valid phone numbers.
        """
        limit = args.get("limit", 10)
        require_phone = args.get("require_phone", True)

        try:
            # Query leads with phone numbers, sorted by AI score and recency
            query_sql = """
                SELECT
                    l.id,
                    l.first_name,
                    l.last_name,
                    l.name,
                    l.phone,
                    l.email,
                    l.ai_score,
                    l.stage,
                    l.source,
                    l.loan_amount,
                    l.created_at,
                    l.last_contact,
                    l.notes
                FROM leads l
                WHERE l.stage NOT IN ('Withdrawn', 'Does Not Qualify')
                  AND l.owner_id = :user_id
                  AND (:org_id IS NULL OR l.organization_id = :org_id)
            """

            if require_phone:
                query_sql += " AND l.phone IS NOT NULL AND l.phone != ''"

            # Sort by AI score (desc), then by stage priority, then by recency
            query_sql += """
                ORDER BY
                    COALESCE(l.ai_score, 50) DESC,
                    CASE l.stage
                        WHEN 'New' THEN 100
                        WHEN 'Attempted Contact' THEN 90
                        WHEN 'Prospect' THEN 80
                        WHEN 'Application' THEN 70
                        WHEN 'Pre-Qualified' THEN 60
                        WHEN 'Pre-Approved' THEN 50
                        ELSE 10
                    END DESC,
                    l.created_at DESC
                LIMIT :limit
            """

            rows = db.execute(text(query_sql), {"user_id": current_user.id, "org_id": org_id, "limit": limit}).fetchall()

            top_leads = []
            for i, row in enumerate(rows, 1):
                name = f"{row.first_name or ''} {row.last_name or ''}".strip() or row.name or "Unknown"

                top_leads.append({
                    "rank": i,
                    "id": row.id,
                    "name": name,
                    "phone": row.phone,
                    "email": row.email,
                    "score": row.ai_score or 50,
                    "stage": row.stage,
                    "source": row.source,
                    "loan_amount": float(row.loan_amount) if row.loan_amount else None,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "last_contact": row.last_contact.isoformat() if row.last_contact else None,
                    "notes": row.notes[:200] if row.notes else None,
                    "call_ready": True
                })

            # Summary stats
            avg_score = sum(l["score"] for l in top_leads) / len(top_leads) if top_leads else 0
            stages = {}
            for lead in top_leads:
                stages[lead["stage"]] = stages.get(lead["stage"], 0) + 1

            return {
                "total": len(top_leads),
                "leads": top_leads,
                "summary": {
                    "average_score": round(avg_score, 1),
                    "by_stage": stages,
                    "all_have_phone": True
                },
                "call_action": {
                    "ready_to_dial": len(top_leads),
                    "suggestion": f"Click to call any of these {len(top_leads)} leads directly"
                }
            }

        except Exception as e:
            logger.error(f"Error in get_top_leads: {e}")
            db.rollback()
            return {"error": "Internal server error", "leads": []}

    tools["get_top_leads"] = execute_get_top_leads

    async def execute_get_stale_leads(args):
        """
        Get leads that haven't been contacted in a specified number of days.

        Useful for:
        - Re-engagement campaigns
        - Preventing leads from going cold
        - Identifying follow-up opportunities
        """
        days_threshold = args.get("days_threshold", 7)
        limit = args.get("limit", 50)
        include_never_contacted = args.get("include_never_contacted", True)

        try:
            now = datetime.now()
            threshold_date = now - timedelta(days=days_threshold)

            # Build query for stale leads
            if include_never_contacted:
                query_sql = """
                    SELECT
                        l.id,
                        l.first_name,
                        l.last_name,
                        l.name,
                        l.phone,
                        l.email,
                        l.ai_score,
                        l.stage,
                        l.source,
                        l.loan_amount,
                        l.created_at,
                        l.last_contact
                    FROM leads l
                    WHERE l.stage NOT IN ('Withdrawn', 'Does Not Qualify')
                      AND l.owner_id = :user_id
                      AND (:org_id IS NULL OR l.organization_id = :org_id)
                      AND (l.last_contact IS NULL OR l.last_contact < :threshold)
                    ORDER BY l.last_contact ASC NULLS FIRST
                    LIMIT :limit
                """
            else:
                query_sql = """
                    SELECT
                        l.id,
                        l.first_name,
                        l.last_name,
                        l.name,
                        l.phone,
                        l.email,
                        l.ai_score,
                        l.stage,
                        l.source,
                        l.loan_amount,
                        l.created_at,
                        l.last_contact
                    FROM leads l
                    WHERE l.stage NOT IN ('Withdrawn', 'Does Not Qualify')
                      AND l.owner_id = :user_id
                      AND (:org_id IS NULL OR l.organization_id = :org_id)
                      AND l.last_contact IS NOT NULL
                      AND l.last_contact < :threshold
                    ORDER BY l.last_contact ASC
                    LIMIT :limit
                """

            rows = db.execute(text(query_sql), {
                "user_id": current_user.id,
                "org_id": org_id,
                "threshold": threshold_date,
                "limit": limit
            }).fetchall()

            stale_leads = []
            never_contacted_count = 0

            for row in rows:
                name = f"{row.first_name or ''} {row.last_name or ''}".strip() or row.name or "Unknown"

                if row.last_contact:
                    days_since = (now - row.last_contact).days
                else:
                    days_since = None
                    never_contacted_count += 1

                stale_leads.append({
                    "id": row.id,
                    "name": name,
                    "phone": row.phone,
                    "email": row.email,
                    "source": row.source,
                    "stage": row.stage,
                    "loan_amount": float(row.loan_amount) if row.loan_amount else None,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "last_contact": row.last_contact.isoformat() if row.last_contact else None,
                    "days_since_contact": days_since,
                    "never_contacted": row.last_contact is None,
                    "priority": "high" if days_since is None or days_since > 14 else "medium"
                })

            return {
                "total": len(stale_leads),
                "never_contacted_count": never_contacted_count,
                "days_threshold": days_threshold,
                "leads": stale_leads,
                "summary": {
                    "total_stale": len(stale_leads),
                    "never_contacted": never_contacted_count,
                    "contacted_but_stale": len(stale_leads) - never_contacted_count,
                    "high_priority": len([l for l in stale_leads if l["priority"] == "high"])
                }
            }

        except Exception as e:
            logger.error(f"Error in get_stale_leads: {e}")
            db.rollback()
            return {"error": "Internal server error", "leads": []}

    tools["get_stale_leads"] = execute_get_stale_leads

    # ============ Communication Tools ============

    async def execute_click_to_dial(args):
        """
        Initiate an outbound call to a contact using click-to-dial.

        Args:
            phone_number: The phone number to call (required)
            contact_name: Name of the person being called (optional)
            lead_id: Associated lead ID (optional)
            loan_id: Associated loan ID (optional)
        """
        import os
        from telephony.dialer_engine import click_to_dial

        phone_number = args.get("phone_number")
        if not phone_number:
            return {"success": False, "error": "phone_number is required"}

        # Clean phone number - remove any non-digit characters except +
        clean_phone = "".join(c for c in phone_number if c.isdigit() or c == "+")
        if not clean_phone.startswith("+"):
            clean_phone = f"+1{clean_phone}" if len(clean_phone) == 10 else f"+{clean_phone}"

        contact_name = args.get("contact_name", "Contact")
        lead_id = args.get("lead_id")
        loan_id = args.get("loan_id")

        base_url = os.getenv("BASE_URL", "https://app.perenniaai.com")

        try:
            result = click_to_dial(
                db_session=db,
                agent_id=current_user.id,
                phone_number=clean_phone,
                contact_name=contact_name,
                base_url=base_url,
                lead_id=lead_id,
                loan_id=loan_id
            )

            if result.get("success"):
                return {
                    "success": True,
                    "message": f"Call initiated to {contact_name} at {clean_phone}",
                    "call_sid": result.get("call_sid"),
                    "phone_number": clean_phone,
                    "contact_name": contact_name
                }
            else:
                return {
                    "success": False,
                    "error": result.get("error", "Failed to initiate call"),
                    "phone_number": clean_phone
                }
        except Exception as e:
            logger.error(f"Error in click_to_dial: {e}")
            return {"success": False, "error": "Internal server error"}

    tools["click_to_dial"] = execute_click_to_dial
    tools["make_call"] = execute_click_to_dial  # Alias for natural language
    tools["call_contact"] = execute_click_to_dial  # Another alias

    async def execute_send_sms(args):
        """
        Send an SMS message to a phone number.

        Args:
            phone_number: The phone number to text (required)
            message: The message content (required)
            lead_id: Associated lead ID (optional)
            loan_id: Associated loan ID (optional)
        """
        from integrations.sms_service import get_sms_client

        sms_client = get_sms_client(db=db, user_id=current_user.id)
        phone_number = args.get("phone_number") or args.get("to_number")
        message = args.get("message")

        if not phone_number:
            return {"success": False, "error": "phone_number is required"}
        if not message:
            return {"success": False, "error": "message is required"}

        # Clean phone number
        clean_phone = "".join(c for c in phone_number if c.isdigit() or c == "+")
        if not clean_phone.startswith("+"):
            clean_phone = f"+1{clean_phone}" if len(clean_phone) == 10 else f"+{clean_phone}"

        # TCPA compliance: use verified sender with consent + DNC checks
        try:
            from telephony.sms import send_sms_verified
            result = send_sms_verified(
                to=clean_phone,
                text=message,
                user_id=current_user.id,
                organization_id=org_id,
            )
            message_sid = result.get("id") if isinstance(result, dict) else result

            if message_sid and result.get("status") == "sent":
                # Log to database
                try:
                    from database.models import SMSMessage
                    sms_record = SMSMessage(
                        user_id=current_user.id,
                        lead_id=args.get("lead_id"),
                        loan_id=args.get("loan_id"),
                        to_number=clean_phone,
                        from_number=sms_client.from_number,
                        message=message,
                        direction="outbound",
                        status="sent",
                        provider_message_id=message_sid
                    )
                    db.add(sms_record)
                    db.commit()
                except Exception as log_err:
                    logger.warning(f"Failed to log SMS: {log_err}")

                return {
                    "success": True,
                    "message": f"SMS sent to {clean_phone}",
                    "message_sid": message_sid,
                    "phone_number": clean_phone
                }
            else:
                return {
                    "success": False,
                    "error": "Failed to send SMS - check telephony provider configuration",
                    "phone_number": clean_phone
                }
        except Exception as e:
            logger.error(f"Error in send_sms: {e}")
            return {"success": False, "error": "Internal server error"}

    tools["send_sms"] = execute_send_sms
    tools["send_text"] = execute_send_sms  # Alias for natural language
    tools["text_contact"] = execute_send_sms  # Another alias

    async def execute_bulk_lead_outreach(args):
        """
        Send bulk text messages to leads and create follow-up tasks.

        Args:
            lead_status: Status of leads to contact (e.g., "NEW", "ATTEMPTED_CONTACT")
            message_template: Message to send (can include {name} placeholder)
            include_calendar_link: Whether to include user's calendar booking link
            create_followup_tasks: Whether to create tasks for non-responders
        """
        from sqlalchemy import text
        from database import SessionLocal

        lead_status = args.get("lead_status", "NEW")
        message_template = args.get("message_template", "")
        include_calendar_link = args.get("include_calendar_link", True)
        create_followup_tasks = args.get("create_followup_tasks", True)

        if not message_template:
            message_template = "Hi {name}, this is your loan officer. I'd love to schedule a time to discuss your mortgage needs. When works best for you?"

        db = SessionLocal()
        results = {
            "leads_found": 0,
            "texts_sent": 0,
            "texts_failed": 0,
            "tasks_created": 0,
            "leads_contacted": [],
            "leads_no_phone": []
        }

        try:
            # Get leads by status — scoped to current user + tenant
            query = text("""
                SELECT id, first_name, last_name, phone, email, stage
                FROM leads
                WHERE stage = :status
                AND owner_id = :user_id
                AND (:org_id IS NULL OR organization_id = :org_id)
                AND phone IS NOT NULL
                AND phone != ''
                LIMIT 50
            """)
            leads = db.execute(query, {
                "status": lead_status,
                "user_id": current_user.id,
                "org_id": org_id,
            }).fetchall()
            results["leads_found"] = len(leads)

            if not leads:
                return {
                    "success": True,
                    "message": f"No leads found with status '{lead_status}' that have phone numbers.",
                    "data": results
                }

            # Get calendar booking link for user if available
            booking_link = ""
            if include_calendar_link and current_user and hasattr(current_user, 'id'):
                booking_query = text("""
                    SELECT booking_slug FROM users WHERE id = :user_id
                """)
                user_result = db.execute(booking_query, {"user_id": current_user.id}).fetchone()
                if user_result and user_result.booking_slug:
                    booking_link = f"\n\nBook a time here: https://perenniaai.com/book/{user_result.booking_slug}"

            # TCPA compliance: use verified sender with consent + DNC checks
            from telephony.sms import send_sms_verified

            for lead in leads:
                lead_id, first_name, last_name, phone, email, stage = lead
                name = f"{first_name or ''} {last_name or ''}".strip() or "there"

                if not phone:
                    results["leads_no_phone"].append({"id": lead_id, "name": name})
                    continue

                # Personalize message
                message = message_template.replace("{name}", first_name or name)
                message += booking_link

                try:
                    # Send SMS via TCPA-compliant verified sender
                    sms_result = send_sms_verified(
                        to=phone,
                        text=message,
                        user_id=current_user.id,
                        organization_id=org_id,
                    )
                    sid = sms_result.get("id") if isinstance(sms_result, dict) else sms_result
                    if sid:
                        results["texts_sent"] += 1
                        results["leads_contacted"].append({
                            "id": lead_id,
                            "name": name,
                            "phone": phone,
                            "message_sid": sid
                        })

                        # Log communication
                        log_query = text("""
                            INSERT INTO communications (lead_id, type, direction, content, status, created_at)
                            VALUES (:lead_id, 'sms', 'outbound', :content, 'sent', NOW())
                        """)
                        db.execute(log_query, {"lead_id": lead_id, "content": message})

                        # Create follow-up task if requested
                        if create_followup_tasks:
                            task_query = text("""
                                INSERT INTO tasks (
                                    title, description, due_date, priority, status,
                                    related_to_type, related_to_id, created_at
                                ) VALUES (
                                    :title, :description, NOW() + INTERVAL '2 days',
                                    'medium', 'pending', 'lead', :lead_id, NOW()
                                )
                            """)
                            db.execute(task_query, {
                                "title": f"Follow up with {name} - no SMS response",
                                "description": f"Sent scheduling text on {datetime.now().strftime('%m/%d')}. Follow up if no response.",
                                "lead_id": lead_id
                            })
                            results["tasks_created"] += 1
                    else:
                        results["texts_failed"] += 1
                except Exception as e:
                    logger.error(f"Failed to send SMS to {mask_phone(phone)}: {e}")
                    results["texts_failed"] += 1

            db.commit()

            return {
                "success": True,
                "message": f"Sent {results['texts_sent']} texts to {lead_status} leads. Created {results['tasks_created']} follow-up tasks.",
                "data": results
            }

        except Exception as e:
            db.rollback()
            logger.error(f"Error in bulk_lead_outreach: {e}")
            return {"success": False, "error": "Internal server error"}

    tools["bulk_lead_outreach"] = execute_bulk_lead_outreach

    async def execute_send_email(args):
        """
        Send an email to an external contact via Microsoft Graph.

        CALENDAR-AWARE: If the email is about scheduling (detected via keywords),
        automatically checks the user's calendar and injects available time slots
        into the email body before sending.

        Args:
            to_email: Recipient email address (required)
            subject: Email subject line (required)
            body: Email body content (required)
            user_id: User ID for OAuth token lookup (optional, uses current_user if not provided)
            skip_availability: Set to True to skip auto-injecting availability (optional)
        """
        import httpx
        import os
        import re
        from datetime import datetime, timedelta

        to_email = args.get("to_email")
        subject = args.get("subject", "Message from your Loan Officer")
        body = args.get("body", "")
        skip_availability = args.get("skip_availability", False)

        if not to_email:
            return {"success": False, "error": "to_email is required"}
        if not body:
            return {"success": False, "error": "body is required"}

        # Track if we injected availability
        availability_injected = False
        injected_slots = []

        # Helper: Detect if email is about scheduling
        def is_scheduling_email(subj: str, content: str) -> bool:
            scheduling_keywords = [
                r'\bschedul\w*\b', r'\bmeet\w*\b', r'\bappointment\b', r'\bcall\b',
                r'\bavailab\w*\b', r'\bset up a time\b', r'\bfind a time\b',
                r'\bwhen.*free\b', r'\bwhen.*available\b', r'\bdiscuss\b',
                r'\bchat\b', r'\bconnect\b', r'\bconsultation\b'
            ]
            combined = f"{subj} {content}".lower()
            return any(re.search(p, combined, re.IGNORECASE) for p in scheduling_keywords)

        # Helper: Calculate free slots from busy periods
        def calculate_free_slots(busy_slots, days_ahead=5, slots_needed=4):
            free_slots = []
            now = datetime.now()
            start_date = now.date() + timedelta(days=1) if now.hour >= 16 else now.date()

            for day_offset in range(days_ahead):
                check_date = start_date + timedelta(days=day_offset)
                if check_date.weekday() >= 5:  # Skip weekends
                    continue

                for hour in range(9, 17):  # 9 AM to 5 PM
                    for minute in [0, 30]:
                        slot_start = datetime.combine(check_date, datetime.min.time().replace(hour=hour, minute=minute))
                        slot_end = slot_start + timedelta(minutes=30)

                        if slot_start <= now + timedelta(hours=1):
                            continue

                        is_free = True
                        for busy in busy_slots:
                            busy_start = busy.get('start')
                            busy_end = busy.get('end')
                            if isinstance(busy_start, str):
                                busy_start = datetime.fromisoformat(busy_start.replace('Z', '+00:00').replace('+00:00', ''))
                            if isinstance(busy_end, str):
                                busy_end = datetime.fromisoformat(busy_end.replace('Z', '+00:00').replace('+00:00', ''))
                            if hasattr(busy_start, 'replace'):
                                busy_start = busy_start.replace(tzinfo=None)
                            if hasattr(busy_end, 'replace'):
                                busy_end = busy_end.replace(tzinfo=None)
                            if slot_start < busy_end and slot_end > busy_start:
                                is_free = False
                                break

                        if is_free:
                            free_slots.append({
                                'date': check_date.strftime('%A, %B %d'),
                                'start': slot_start.strftime('%I:%M %p'),
                            })
                            if len(free_slots) >= slots_needed:
                                return free_slots
            return free_slots

        # Helper: Inject availability into email body
        def inject_availability(content: str, slots: list) -> str:
            if not slots:
                return content
            avail_text = "\n\nHere are some times I'm available:\n"
            for slot in slots:
                avail_text += f"• {slot['date']} at {slot['start']}\n"
            avail_text += "\nLet me know which time works best for you, or suggest another time that's convenient.\n"

            # Try to insert before sign-off
            for pattern in [r'\n\s*(Best|Best regards|Regards|Thanks|Thank you|Sincerely)', r'\n\s*--\s*\n']:
                match = re.search(pattern, content, re.IGNORECASE)
                if match:
                    return content[:match.start()] + avail_text + content[match.start():]
            return content + avail_text

        try:
            # Check for Microsoft OAuth token in microsoft_oauth_tokens table
            user_id = current_user.id
            logger.info(f"[send_email] Looking up OAuth token for user_id={user_id} (type: {type(user_id).__name__})")

            oauth = db.execute(text("""
                SELECT access_token, refresh_token, token_expires_at
                FROM microsoft_oauth_tokens
                WHERE user_id = :user_id
                AND access_token IS NOT NULL
            """), {"user_id": int(user_id)}).fetchone()

            if not oauth:
                return {
                    "success": False,
                    "error": "Microsoft account not connected. Please connect your Microsoft 365 account in Settings > Outlook Email.",
                    "requires_oauth": True
                }

            access_token = oauth.access_token
            refresh_token = oauth.refresh_token
            expires_at = oauth.token_expires_at

            # Decrypt token if encrypted (tokens are encrypted using SECRET_KEY)
            if access_token and access_token.startswith("gAAAAA"):
                try:
                    from cryptography.fernet import Fernet
                    import base64
                    secret_key = os.getenv("SECRET_KEY", "")
                    key_material = secret_key.encode()[:32].ljust(32, b'0')
                    encryption_key = base64.urlsafe_b64encode(key_material)
                    f = Fernet(encryption_key)
                    access_token = f.decrypt(access_token.encode()).decode()
                    if refresh_token and refresh_token.startswith("gAAAAA"):
                        refresh_token = f.decrypt(refresh_token.encode()).decode()
                except Exception as decrypt_err:
                    logger.error(f"Token decryption failed: {decrypt_err}")
                    return {
                        "success": False,
                        "error": "Failed to decrypt email token. Please reconnect your Microsoft account in Settings > Outlook Email.",
                        "requires_oauth": True
                    }

            # Check if token needs refresh
            if expires_at and expires_at < datetime.now(timezone.utc):
                logger.info("Access token expired, attempting refresh...")
                client_id = os.getenv("MICROSOFT_CLIENT_ID")
                client_secret = os.getenv("MICROSOFT_CLIENT_SECRET")

                if refresh_token and client_id and client_secret:
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        refresh_response = await client.post(
                            "https://login.microsoftonline.com/common/oauth2/v2.0/token",
                            data={
                                "client_id": client_id,
                                "client_secret": client_secret,
                                "refresh_token": refresh_token,
                                "grant_type": "refresh_token",
                                "scope": "Mail.Send Mail.ReadWrite offline_access"
                            },
                            headers={"Content-Type": "application/x-www-form-urlencoded"},
                            timeout=30.0
                        )

                        if refresh_response.status_code == 200:
                            tokens = refresh_response.json()
                            access_token = tokens["access_token"]
                            new_refresh = tokens.get("refresh_token", refresh_token)
                            new_expires = datetime.now(timezone.utc) + timedelta(seconds=tokens.get("expires_in", 3600))

                            # Store new tokens (encrypted using SECRET_KEY)
                            try:
                                from cryptography.fernet import Fernet
                                import base64
                                secret_key = os.getenv("SECRET_KEY", "")
                                key_material = secret_key.encode()[:32].ljust(32, b'0')
                                enc_key = base64.urlsafe_b64encode(key_material)
                                f = Fernet(enc_key)
                                enc_access = f.encrypt(access_token.encode()).decode()
                                enc_refresh = f.encrypt(new_refresh.encode()).decode()

                                db.execute(text("""
                                    UPDATE microsoft_oauth_tokens
                                    SET access_token = :access_token,
                                        refresh_token = :refresh_token,
                                        token_expires_at = :expires_at,
                                        updated_at = :updated_at
                                    WHERE user_id = :user_id
                                """), {
                                    "access_token": enc_access,
                                    "refresh_token": enc_refresh,
                                    "expires_at": new_expires,
                                    "updated_at": datetime.now(timezone.utc),
                                    "user_id": int(user_id)
                                })
                                db.commit()
                            except Exception as store_err:
                                logger.warning(f"Failed to store refreshed token: {store_err}")
                        else:
                            return {
                                "success": False,
                                "error": "Microsoft token expired and refresh failed. Please reconnect your account.",
                                "requires_oauth": True
                            }

            # Auto-inject calendar availability for scheduling emails
            if not skip_availability and is_scheduling_email(subject, body):
                logger.info(f"[send_email] Detected scheduling email - checking calendar availability")
                try:
                    # Get busy slots from Microsoft Graph calendar
                    async with httpx.AsyncClient(timeout=15.0) as cal_client:
                        # First get the user's email
                        me_response = await cal_client.get(
                            "https://graph.microsoft.com/v1.0/me",
                            headers={"Authorization": f"Bearer {access_token}"},
                            timeout=15.0
                        )

                        if me_response.status_code == 200:
                            me_data = me_response.json()
                            user_email = me_data.get("mail") or me_data.get("userPrincipalName")

                            if user_email:
                                # Get calendar schedule for next 7 days
                                start_time = datetime.now(timezone.utc)
                                end_time = start_time + timedelta(days=7)

                                schedule_response = await cal_client.post(
                                    "https://graph.microsoft.com/v1.0/me/calendar/getSchedule",
                                    headers={
                                        "Authorization": f"Bearer {access_token}",
                                        "Content-Type": "application/json"
                                    },
                                    json={
                                        "schedules": [user_email],
                                        "startTime": {"dateTime": start_time.isoformat(), "timeZone": "UTC"},
                                        "endTime": {"dateTime": end_time.isoformat(), "timeZone": "UTC"},
                                        "availabilityViewInterval": 30
                                    },
                                    timeout=30.0
                                )

                                if schedule_response.status_code == 200:
                                    schedule_data = schedule_response.json()
                                    busy_slots = []
                                    for schedule in schedule_data.get("value", []):
                                        for item in schedule.get("scheduleItems", []):
                                            busy_slots.append({
                                                "start": item["start"]["dateTime"],
                                                "end": item["end"]["dateTime"]
                                            })

                                    # Calculate free slots
                                    free_slots = calculate_free_slots(busy_slots, days_ahead=5, slots_needed=4)

                                    if free_slots:
                                        body = inject_availability(body, free_slots)
                                        availability_injected = True
                                        injected_slots = free_slots
                                        logger.info(f"[send_email] Injected {len(free_slots)} available time slots into email")
                                    else:
                                        logger.info("[send_email] No free slots found to inject")
                                else:
                                    logger.warning(f"[send_email] Calendar API returned {schedule_response.status_code}")

                except Exception as cal_err:
                    logger.warning(f"[send_email] Could not get calendar availability: {cal_err}")
                    # Continue without availability - don't block the email

            # Send email via Microsoft Graph
            async with httpx.AsyncClient(timeout=30.0) as client:
                email_data = {
                    "message": {
                        "subject": subject,
                        "body": {
                            "contentType": "Text",
                            "content": body
                        },
                        "toRecipients": [
                            {"emailAddress": {"address": to_email}}
                        ]
                    },
                    "saveToSentItems": "true"
                }

                response = await client.post(
                    "https://graph.microsoft.com/v1.0/me/sendMail",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json"
                    },
                    json=email_data,
                    timeout=30.0
                )

                if response.status_code == 202:
                    # Log the sent email
                    try:
                        db.execute(text("""
                            INSERT INTO communications (
                                type, direction, user_id, to_address,
                                subject, body_preview, status, sent_at, created_at
                            ) VALUES (
                                'email', 'outbound', :user_id, :to_email,
                                :subject, :body_preview, 'sent', NOW(), NOW()
                            )
                        """), {
                            "user_id": current_user.id,
                            "to_email": to_email,
                            "subject": subject,
                            "body_preview": body[:500]
                        })
                        db.commit()
                    except Exception as log_err:
                        logger.warning(f"Failed to log email: {log_err}")

                    result = {
                        "success": True,
                        "message": f"Email sent successfully to {to_email}",
                        "to_email": to_email,
                        "subject": subject
                    }

                    # Include availability injection info
                    if availability_injected:
                        result["availability_injected"] = True
                        result["injected_slots"] = [f"{s['date']} at {s['start']}" for s in injected_slots]
                        result["message"] += f" (included {len(injected_slots)} available time slots)"

                    return result
                else:
                    error_text = response.text
                    logger.error(f"Microsoft Graph sendMail failed: {response.status_code} - {error_text}")
                    return {
                        "success": False,
                        "error": f"Failed to send email: {error_text}",
                        "status_code": response.status_code
                    }

        except Exception as e:
            logger.error(f"Error in send_email: {e}")
            return {"success": False, "error": "Internal server error"}

    tools["send_email"] = execute_send_email

    # ============ Historical Analytics Tools ============
    # Import and wrap the historical tools from the tools module

    from .tools.historical import (
        get_performance_by_period as _get_performance_by_period,
        compare_periods as _compare_periods,
        get_data_availability as _get_data_availability,
    )

    async def execute_get_performance_by_period(args):
        """Get performance metrics for a specific time period."""
        period = args.get("period", "this month")
        lo_id = args.get("lo_id")
        try:
            result = _get_performance_by_period(period=period, lo_id=lo_id)
            if hasattr(result, 'to_dict'):
                return result.to_dict()
            return result
        except Exception as e:
            logger.error(f"Error in get_performance_by_period: {e}")
            return {"status": "error", "error": "Internal server error"}

    tools["get_performance_by_period"] = execute_get_performance_by_period

    async def execute_compare_periods(args):
        """Compare performance between two time periods."""
        period1 = args.get("period1", "last month")
        period2 = args.get("period2", "this month")
        lo_id = args.get("lo_id")
        try:
            result = _compare_periods(period1=period1, period2=period2, lo_id=lo_id)
            if hasattr(result, 'to_dict'):
                return result.to_dict()
            return result
        except Exception as e:
            logger.error(f"Error in compare_periods: {e}")
            return {"status": "error", "error": "Internal server error"}

    tools["compare_periods"] = execute_compare_periods

    async def execute_get_data_availability(args):
        """Get information about available historical data."""
        try:
            result = _get_data_availability()
            if hasattr(result, 'to_dict'):
                return result.to_dict()
            return result
        except Exception as e:
            logger.error(f"Error in get_data_availability: {e}")
            return {"status": "error", "error": "Internal server error"}

    tools["get_data_availability"] = execute_get_data_availability

    # ============ Email Intelligence Tools ============
    # Tool to check inbox for emails needing response

    from .tools.email_intel import get_emails_needing_response as _get_emails_needing_response

    async def execute_get_emails_needing_response(args):
        """Get emails from inbox that need a response."""
        # Pass the current user's ID for email lookup
        user_id = current_user.id if hasattr(current_user, 'id') else None
        days = args.get("days", 7)
        unread_only = args.get("unread_only", True)
        limit = args.get("limit", 20)

        try:
            result = _get_emails_needing_response(
                user_id=user_id,
                days=days,
                unread_only=unread_only,
                limit=limit
            )
            if hasattr(result, 'to_dict'):
                return result.to_dict()
            return result
        except Exception as e:
            logger.error(f"Error in get_emails_needing_response: {e}")
            return {"status": "error", "error": "Internal server error"}

    tools["get_emails_needing_response"] = execute_get_emails_needing_response

    # Tool to search user's email inbox via Microsoft Graph
    from .tools.email_intel import search_email_inbox as _search_email_inbox

    async def execute_search_email_inbox(args):
        """Search user's Microsoft 365 email inbox for messages."""
        user_id = current_user.id if hasattr(current_user, 'id') else None
        search_query = args.get("search_query", "")
        limit = args.get("limit", 10)
        folder = args.get("folder", "all")

        try:
            result = _search_email_inbox(
                search_query=search_query,
                user_id=user_id,
                limit=limit,
                folder=folder
            )
            if hasattr(result, 'to_dict'):
                return result.to_dict()
            return result
        except Exception as e:
            logger.error(f"Error in search_email_inbox: {e}")
            return {"status": "error", "error": "Internal server error"}

    tools["search_email_inbox"] = execute_search_email_inbox

    # Tool to create referral partners
    from .tools.customer import create_referral_partner as _create_referral_partner

    async def execute_create_referral_partner(args):
        """Create or add a referral partner to the CRM."""
        user_id = current_user.id if hasattr(current_user, 'id') else None
        name = args.get("name", "")
        email = args.get("email", "")
        phone = args.get("phone")
        company = args.get("company")
        partner_type = args.get("partner_type", "realtor")
        notes = args.get("notes")

        try:
            result = _create_referral_partner(
                name=name,
                email=email,
                phone=phone,
                company=company,
                partner_type=partner_type,
                notes=notes,
                user_id=user_id
            )
            if hasattr(result, 'to_dict'):
                return result.to_dict()
            return result
        except Exception as e:
            logger.error(f"Error in create_referral_partner: {e}")
            return {"status": "error", "error": "Internal server error"}

    tools["create_referral_partner"] = execute_create_referral_partner

    # -----------------------------------------------------------------
    # sendPushNotification — Push notification to user's mobile device
    # -----------------------------------------------------------------

    async def execute_send_push_notification(
        user_id: int,
        title: str,
        body: str,
        notification_type: str = "general",
        priority: str = "normal",
        loan_id: int = None,
    ) -> Dict[str, Any]:
        """Send a push notification to a user's registered mobile devices.

        Respects rate limits (max 5/user/hour), quiet hours, and user preferences.
        """
        try:
            from services.agent_notification_service import get_agent_notification_service
            push_svc = get_agent_notification_service()

            data_payload = {"type": notification_type}
            if loan_id:
                data_payload["entity_id"] = str(loan_id)
                data_payload["entity_type"] = "loan"
                data_payload["route"] = f"/loans/{loan_id}"

            result = push_svc.notify_user(
                db=db,
                user_id=user_id,
                title=title,
                body=body,
                notification_type=notification_type,
                data=data_payload,
                priority=priority,
            )

            return {
                "status": "success",
                "sent": result.get("sent", 0),
                "failed": result.get("failed", 0),
                "skipped": result.get("skipped", 0),
                "reason": result.get("reason"),
            }
        except Exception as e:
            logger.error(f"Error in sendPushNotification: {e}")
            return {"status": "error", "error": str(e), "sent": 0}

    tools["sendPushNotification"] = execute_send_push_notification

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

    # Register tools — merge registry tools with inline tools
    # Inline tools (with db/user context) take precedence over registry tools
    try:
        from .dynamic_tool_loader import create_all_tools
        tool_functions = create_all_tools(db, current_user)
    except ImportError:
        # Fallback to inline-only if dynamic loader not available
        tool_functions = create_tool_functions_from_main(db, current_user)
    service.register_tools(tool_functions)

    return service
