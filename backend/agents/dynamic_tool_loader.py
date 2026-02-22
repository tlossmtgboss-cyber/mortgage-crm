"""
Dynamic Tool Loader - Intent-Based Agent Tool Loading

This module provides dynamic tool loading based on classified intent.
Instead of loading all 160 tools, it loads only 8-16 tools from 1-2 relevant agents.

Performance Impact:
- Before: All 160 tools sent to LLM context
- After: Only 8-16 relevant tools loaded based on intent
- Reduction: 90%+ fewer tools, faster context processing

Usage:
    from agents.dynamic_tool_loader import get_tools_for_intent, create_scoped_tools

    # Get tool names for an intent
    tool_names = get_tools_for_intent("leads")
    # Returns: ["get_lead_details", "score_lead", "suggest_followup", ...]

    # Create executable tool functions
    tools = create_scoped_tools(db, current_user, intent="leads")
    # Returns: Dict[str, Callable] with only lead_nurturer tools
"""

import logging
from typing import Any, Callable, Dict, List, Optional
from sqlalchemy.orm import Session

from .intent_router import INTENT_TO_AGENTS
from .tool_integration import AGENT_CONFIGS

logger = logging.getLogger(__name__)


# =============================================================================
# BASE TOOLS (Always Available)
# =============================================================================

# These base tools are always loaded regardless of intent
# They provide fundamental CRM capabilities
BASE_TOOL_NAMES = [
    "get_pipeline",
    "get_tasks",
    "search_leads",
    "search_loans",
    "create_task",
    "get_daily_priorities",
]


# =============================================================================
# INTENT TO TOOL MAPPING
# =============================================================================

def get_agent_tool_names(agent_name: str) -> List[str]:
    """
    Get the list of tool names for a specific agent.

    Args:
        agent_name: Name of the agent (e.g., "pipeline_analyst", "lead_nurturer")

    Returns:
        List of tool names available to this agent
    """
    config = AGENT_CONFIGS.get(agent_name)
    if config:
        return config.tool_names.copy()
    return []


def get_tools_for_intent(intent: str) -> List[str]:
    """
    Get all tool names for agents mapped to an intent.

    Args:
        intent: Classified intent (e.g., "leads", "pipeline", "tasks")

    Returns:
        List of unique tool names from all relevant agents
    """
    agents = INTENT_TO_AGENTS.get(intent, INTENT_TO_AGENTS["general"])

    tool_names = set(BASE_TOOL_NAMES)  # Start with base tools

    for agent_name in agents:
        agent_tools = get_agent_tool_names(agent_name)
        tool_names.update(agent_tools)

    logger.info(f"[TOOL_LOADER] Intent '{intent}' -> Agents {agents} -> {len(tool_names)} tools")
    return list(tool_names)


def get_tool_count_for_intent(intent: str) -> int:
    """Get the total number of tools that would be loaded for an intent."""
    return len(get_tools_for_intent(intent))


# =============================================================================
# TOOL REGISTRY BRIDGE
# =============================================================================

def create_tool_functions_from_registry(
    agent_role: Optional[str] = None,
) -> Dict[str, Callable]:
    """
    Bridge: wrap @mortgage_tool registry functions as async callables.

    The tool_registry contains 160+ tools registered via the @mortgage_tool
    decorator in agents/tools/. This function wraps each sync tool function
    in an async wrapper and translates ToolResult to plain dict, making
    them compatible with the LangGraph gather node.

    Args:
        agent_role: Optional role filter (e.g., "pipeline_analyst").
                    If None, returns all registered tools.

    Returns:
        Dict mapping tool name to async callable(args) -> dict
    """
    try:
        from .tools import tool_registry
    except ImportError:
        logger.warning("[TOOL_LOADER] Could not import tool_registry — registry bridge disabled")
        return {}

    if agent_role:
        tool_defs = tool_registry.get_for_agent(agent_role)
        registry_tools = {td.name: td for td in tool_defs}
    else:
        registry_tools = tool_registry.get_all()

    wrapped = {}

    for name, tool_def in registry_tools.items():
        fn = tool_def.func
        # Create async wrapper that converts ToolResult → dict
        async def _async_wrapper(args, _fn=fn, _name=name):
            try:
                result = _fn(**args) if isinstance(args, dict) else _fn(args)
                # ToolResult objects have a .to_dict() method
                if hasattr(result, 'to_dict'):
                    return result.to_dict()
                if isinstance(result, dict):
                    return result
                return {"status": "success", "data": result}
            except Exception as e:
                logger.error(f"Registry tool '{_name}' failed: {e}")
                return {"status": "error", "error": str(e)}

        wrapped[name] = _async_wrapper

    logger.info(
        f"[TOOL_LOADER] Loaded {len(wrapped)} tools from registry"
        + (f" (role={agent_role})" if agent_role else "")
    )
    return wrapped


# =============================================================================
# DYNAMIC TOOL CREATION
# =============================================================================

def create_scoped_tools(
    db: Session,
    current_user: Any,
    intent: str = "general",
    include_base: bool = True
) -> Dict[str, Callable]:
    """
    Create tool functions scoped to a specific intent.

    This is the main entry point for dynamic tool loading. It creates
    only the tool functions needed for the classified intent, merging
    inline tools (from service.py) with registry tools (from @mortgage_tool).

    Args:
        db: Database session
        current_user: Current authenticated user
        intent: Classified intent from intent_router
        include_base: Whether to include base tools

    Returns:
        Dictionary mapping tool names to async callable functions
    """
    from .service import create_tool_functions_from_main

    # Layer 1: Registry tools (160+ tools, no db/user context)
    all_tools = create_tool_functions_from_registry()

    # Layer 2: Inline tools (26 tools with db/user context — take precedence)
    inline_tools = create_tool_functions_from_main(db, current_user)
    all_tools.update(inline_tools)

    # Get tool names for this intent
    needed_tools = get_tools_for_intent(intent)

    # Filter to only needed tools
    scoped_tools = {}
    for name in needed_tools:
        if name in all_tools:
            scoped_tools[name] = all_tools[name]

    # Log what we're loading
    loaded = list(scoped_tools.keys())
    not_found = [n for n in needed_tools if n not in all_tools]

    if not_found:
        logger.debug(f"[TOOL_LOADER] Tools not implemented yet: {not_found}")

    logger.info(
        f"[TOOL_LOADER] Loaded {len(scoped_tools)} tools for intent '{intent}': {loaded}"
    )

    return scoped_tools


def create_all_tools(db: Session, current_user: Any) -> Dict[str, Callable]:
    """
    Create all available tool functions.

    Merges inline tools (with db/user context) with registry tools
    (stateless). Inline tools take precedence for duplicate names.

    Args:
        db: Database session
        current_user: Current authenticated user

    Returns:
        Dictionary of all available tool functions
    """
    from .service import create_tool_functions_from_main

    # Registry tools first (lower priority)
    all_tools = create_tool_functions_from_registry()

    # Inline tools override (higher priority — have db/user context)
    inline_tools = create_tool_functions_from_main(db, current_user)
    all_tools.update(inline_tools)

    logger.info(f"[TOOL_LOADER] Total tools available: {len(all_tools)}")
    return all_tools


# =============================================================================
# TOOL REGISTRY INFO
# =============================================================================

def get_intent_tool_summary() -> Dict[str, Dict]:
    """
    Get a summary of tools by intent for debugging/logging.

    Returns:
        Dict mapping intent -> {agents, tool_count, tools}
    """
    summary = {}

    for intent, agents in INTENT_TO_AGENTS.items():
        tools = get_tools_for_intent(intent)
        summary[intent] = {
            "agents": agents,
            "tool_count": len(tools),
            "tools": tools,
        }

    return summary


def print_tool_loading_stats():
    """Print statistics about tool loading for debugging."""
    print("=" * 70)
    print("DYNAMIC TOOL LOADING SUMMARY")
    print("=" * 70)

    total_unique_tools = set()

    for intent, agents in INTENT_TO_AGENTS.items():
        tools = get_tools_for_intent(intent)
        total_unique_tools.update(tools)

        print(f"\n{intent.upper()}")
        print(f"  Agents: {', '.join(agents)}")
        print(f"  Tools: {len(tools)}")

    print("\n" + "=" * 70)
    print(f"Total unique tools: {len(total_unique_tools)}")
    print(f"Total agents: {len(AGENT_CONFIGS)}")

    # Calculate average tools per intent
    tool_counts = [len(get_tools_for_intent(i)) for i in INTENT_TO_AGENTS]
    avg_tools = sum(tool_counts) / len(tool_counts)
    print(f"Average tools per intent: {avg_tools:.1f}")
    print("=" * 70)


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    "BASE_TOOL_NAMES",
    "get_agent_tool_names",
    "get_tools_for_intent",
    "get_tool_count_for_intent",
    "create_scoped_tools",
    "create_all_tools",
    "get_intent_tool_summary",
    "print_tool_loading_stats",
]
