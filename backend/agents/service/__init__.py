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

    Thin wrapper that delegates to the per-domain builders in
    ``backend.agents.service.tools_factory``. Kept here for backward
    compatibility with all existing importers (including
    ``dynamic_tool_loader`` and ``routes.chat_screenshot_routes``).

    Args:
        db: Database session
        current_user: Current user object

    Returns:
        Dictionary mapping tool names to async functions
    """
    from .tools_factory import build_tool_functions
    return build_tool_functions(db, current_user)


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
