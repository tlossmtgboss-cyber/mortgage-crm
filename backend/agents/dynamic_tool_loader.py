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
    only the tool functions needed for the classified intent.

    Args:
        db: Database session
        current_user: Current authenticated user
        intent: Classified intent from intent_router
        include_base: Whether to include base tools

    Returns:
        Dictionary mapping tool names to async callable functions
    """
    from .service import create_tool_functions_from_main

    # Start with base tools
    all_tools = create_tool_functions_from_main(db, current_user)

    # Get tool names for this intent
    needed_tools = get_tools_for_intent(intent)

    # Filter to only needed tools (from base tools that exist)
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

    Use this when you need the full toolset (e.g., for streaming chat
    that might handle any query type).

    Args:
        db: Database session
        current_user: Current authenticated user

    Returns:
        Dictionary of all available tool functions
    """
    from .service import create_tool_functions_from_main
    return create_tool_functions_from_main(db, current_user)


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
