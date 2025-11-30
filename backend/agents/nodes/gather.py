"""
Data Gatherer Node

This node executes the required tools identified by the Query Analyzer
and consolidates the results into structured data for reasoning.
"""

import asyncio
import logging
import time
from typing import Any, Callable, Dict, Optional
from datetime import datetime

from ..state import (
    AgentState,
    ToolCall,
    add_node_trace,
    add_error,
    update_state
)

logger = logging.getLogger(__name__)


class ToolRegistry:
    """
    Registry for tool implementations that can be called by the Data Gatherer.

    This bridges LangGraph to the existing tool implementations in main.py.
    Tools are registered at runtime with the FastAPI dependency injection context.
    """

    def __init__(self):
        self._tools: Dict[str, Callable] = {}
        self._tool_metadata: Dict[str, dict] = {}

    def register(self, name: str, func: Callable, metadata: dict = None):
        """Register a tool function"""
        self._tools[name] = func
        self._tool_metadata[name] = metadata or {}

    def get(self, name: str) -> Optional[Callable]:
        """Get a tool function by name"""
        return self._tools.get(name)

    def list_tools(self) -> list:
        """List all registered tools"""
        return list(self._tools.keys())

    def get_metadata(self, name: str) -> dict:
        """Get metadata for a tool"""
        return self._tool_metadata.get(name, {})


# Global tool registry - will be populated by FastAPI endpoint
tool_registry = ToolRegistry()


async def execute_tool(
    tool_name: str,
    arguments: dict,
    tool_functions: Dict[str, Callable]
) -> ToolCall:
    """
    Execute a single tool and capture its result.

    Args:
        tool_name: Name of the tool to execute
        arguments: Arguments to pass to the tool
        tool_functions: Dictionary of available tool functions

    Returns:
        ToolCall object with result or error
    """
    tool_call = ToolCall(
        tool_name=tool_name,
        arguments=arguments
    )

    start_time = time.time()

    try:
        func = tool_functions.get(tool_name)
        if func is None:
            tool_call.error = f"Tool '{tool_name}' not found"
            logger.warning(f"Tool not found: {tool_name}")
            return tool_call

        # Execute the tool (handle both sync and async)
        if asyncio.iscoroutinefunction(func):
            result = await func(arguments)
        else:
            result = func(arguments)

        tool_call.result = result
        tool_call.execution_time_ms = (time.time() - start_time) * 1000

        logger.info(f"Tool {tool_name} executed in {tool_call.execution_time_ms:.1f}ms")

    except Exception as e:
        tool_call.error = str(e)
        tool_call.execution_time_ms = (time.time() - start_time) * 1000
        logger.error(f"Tool {tool_name} failed: {e}")

    return tool_call


def determine_tool_arguments(
    tool_name: str,
    state: AgentState
) -> dict:
    """
    Determine arguments for a tool based on query entities and context.

    Args:
        tool_name: Name of the tool
        state: Current agent state with extracted entities

    Returns:
        Arguments dict for the tool
    """
    entities = state.get("query_entities", {})
    args = {}

    # Map entities to tool arguments based on tool type
    if tool_name == "search_loans":
        if entities.get("loan_ids"):
            args["query"] = entities["loan_ids"][0]
        elif entities.get("borrower_names"):
            args["query"] = entities["borrower_names"][0]
        args["limit"] = 10

    elif tool_name == "search_leads":
        if entities.get("borrower_names"):
            args["query"] = entities["borrower_names"][0]
        args["limit"] = 10

    elif tool_name == "get_tasks":
        args["timeframe"] = "today"  # Default to today
        if entities.get("dates"):
            date_ref = entities["dates"][0].lower()
            if "tomorrow" in date_ref:
                args["timeframe"] = "tomorrow"
            elif "week" in date_ref:
                args["timeframe"] = "this_week"
            elif "overdue" in date_ref:
                args["timeframe"] = "overdue"

    elif tool_name == "get_pipeline":
        args["include_details"] = True  # Always include details for better analysis

    elif tool_name == "get_pipeline_metrics":
        pass  # No arguments needed

    elif tool_name == "get_daily_priorities":
        pass  # No arguments needed

    elif tool_name == "get_rate_lock_advisory":
        # Extract days to close from entities
        args["days_to_close"] = 30  # Default to 30 days
        if entities.get("dates"):
            date_ref = entities["dates"][0].lower()
            if "7" in date_ref or "week" in date_ref:
                args["days_to_close"] = 7
            elif "14" in date_ref or "two week" in date_ref:
                args["days_to_close"] = 14
            elif "45" in date_ref:
                args["days_to_close"] = 45
            elif "60" in date_ref:
                args["days_to_close"] = 60

    elif tool_name == "create_task":
        args["title"] = entities.get("task_title", "Follow up")
        args["priority"] = "medium"

    return args


async def gather_data(
    state: AgentState,
    tool_functions: Dict[str, Callable] = None
) -> AgentState:
    """
    Execute required tools and gather data for analysis.

    Args:
        state: Current agent state with required_tools populated
        tool_functions: Dictionary mapping tool names to their implementations

    Returns:
        Updated state with gathered data
    """
    state = add_node_trace(state, "gather")

    if tool_functions is None:
        tool_functions = {}

    # Debug: Log available tools
    available_tool_names = list(tool_functions.keys())
    logger.info(f"[GATHER] Available tool functions: {available_tool_names}")

    required_tools = state.get("required_tools", [])
    logger.info(f"[GATHER] Required tools from analyzer: {required_tools}")

    if not required_tools:
        logger.warning("[GATHER] No tools required, using default pipeline summary")
        required_tools = ["get_pipeline"]

    # Limit concurrent tool calls to avoid overwhelming the system
    MAX_CONCURRENT_TOOLS = 5
    tool_calls = []
    gathered_data = {}
    missing_data = []

    try:
        # Execute tools in batches
        for i in range(0, len(required_tools), MAX_CONCURRENT_TOOLS):
            batch = required_tools[i:i + MAX_CONCURRENT_TOOLS]

            # Create tasks for parallel execution
            tasks = []
            for tool_name in batch:
                # Skip tools not in the provided functions
                if tool_name not in tool_functions:
                    logger.warning(f"[GATHER] Tool {tool_name} not available, skipping. Available: {list(tool_functions.keys())}")
                    missing_data.append(f"Tool not available: {tool_name}")
                    continue

                args = determine_tool_arguments(tool_name, state)
                logger.info(f"[GATHER] Executing tool {tool_name} with args: {args}")
                tasks.append(execute_tool(tool_name, args, tool_functions))

            # Execute batch in parallel
            if tasks:
                results = await asyncio.gather(*tasks, return_exceptions=True)

                for result in results:
                    if isinstance(result, Exception):
                        logger.error(f"Tool execution error: {result}")
                        continue

                    tool_calls.append(result)

                    # Consolidate results into gathered_data
                    if result.result is not None:
                        gathered_data[result.tool_name] = result.result
                    elif result.error:
                        missing_data.append(f"{result.tool_name}: {result.error}")

        # Assess data quality
        total_tools = len(required_tools)
        successful_tools = len([tc for tc in tool_calls if tc.result is not None])

        if successful_tools == 0:
            data_quality = "insufficient"
        elif successful_tools < total_tools * 0.5:
            data_quality = "partial"
        else:
            data_quality = "complete"

        # Update state
        state = update_state(state, {
            "tool_calls": tool_calls,
            "gathered_data": gathered_data,
            "data_quality": data_quality,
            "missing_data": missing_data
        })

        logger.info(f"[GATHER] Data gathering complete: {successful_tools}/{total_tools} tools succeeded")
        logger.info(f"[GATHER] Gathered data keys: {list(gathered_data.keys())}")
        for key, val in gathered_data.items():
            if isinstance(val, dict):
                logger.info(f"[GATHER] {key} sample: {str(val)[:200]}")
            elif isinstance(val, list):
                logger.info(f"[GATHER] {key} count: {len(val)} items")
            else:
                logger.info(f"[GATHER] {key}: {str(val)[:100]}")

        return state

    except Exception as e:
        logger.error(f"Data gathering failed: {e}")
        state = add_error(state, f"Data gathering error: {str(e)}")
        return update_state(state, {
            "tool_calls": tool_calls,
            "gathered_data": gathered_data,
            "data_quality": "insufficient",
            "missing_data": missing_data + [str(e)]
        })


def format_gathered_data_for_llm(state: AgentState) -> str:
    """
    Format gathered data into a string suitable for LLM processing.

    Args:
        state: Agent state with gathered_data populated

    Returns:
        Formatted string of all gathered data
    """
    gathered_data = state.get("gathered_data", {})
    if not gathered_data:
        return "No data was gathered."

    sections = []

    for tool_name, data in gathered_data.items():
        section = f"=== {tool_name.upper().replace('_', ' ')} ===\n"

        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, list):
                    section += f"\n{key}:\n"
                    for item in value[:10]:  # Limit items for context
                        if isinstance(item, dict):
                            item_str = ", ".join(f"{k}: {v}" for k, v in item.items())
                            section += f"  - {item_str}\n"
                        else:
                            section += f"  - {item}\n"
                elif isinstance(value, dict):
                    section += f"\n{key}:\n"
                    for k, v in value.items():
                        section += f"  {k}: {v}\n"
                else:
                    section += f"{key}: {value}\n"
        else:
            section += str(data)

        sections.append(section)

    return "\n\n".join(sections)
