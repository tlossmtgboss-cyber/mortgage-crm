"""
Data Gatherer Node

This node executes the required tools identified by the Query Analyzer
and consolidates the results into structured data for reasoning.

Includes Redis caching for 2-3x speedup on repeat queries.
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

# Import cache - gracefully degrade if not available
try:
    from core.cache import cache
    CACHE_AVAILABLE = True
except ImportError:
    cache = None
    CACHE_AVAILABLE = False

# Import metrics tracker
try:
    from agents.tools.metrics import cache_metrics
    METRICS_AVAILABLE = True
except ImportError:
    cache_metrics = None
    METRICS_AVAILABLE = False

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


# Tools that are safe to cache (read-only, no side effects)
CACHEABLE_TOOLS = {
    "get_pipeline": 300,          # 5 minutes - pipeline summary
    "get_pipeline_metrics": 300,  # 5 minutes - analytics
    "get_daily_priorities": 120,  # 2 minutes - priorities change more often
    "get_rate_lock_advisory": 60, # 1 minute - market-sensitive
    "search_loans": 180,          # 3 minutes - search results
    "search_leads": 180,          # 3 minutes - search results
    "get_tasks": 60,              # 1 minute - tasks change frequently
    "lead_status_insights": 120,  # 2 minutes - lead pipeline coaching
    "get_leads_by_status": 60,    # 1 minute - lead lists change frequently
    "get_top_leads": 60,          # 1 minute - top leads for calling
    "get_stale_leads": 60,        # 1 minute - stale leads for follow-up
}

# Tools that should NEVER be cached (write operations)
NON_CACHEABLE_TOOLS = {
    "create_task", "update_task", "delete_task", "send_email",
    "click_to_dial", "make_call", "call_contact",
    "send_sms", "send_text", "text_contact"
}


async def execute_tool(
    tool_name: str,
    arguments: dict,
    tool_functions: Dict[str, Callable],
    user_id: str = None,
    organization_id: Optional[int] = None,
) -> ToolCall:
    """
    Execute a single tool and capture its result.

    Uses Redis caching for read-only tools to provide 2-3x speedup
    on repeat queries.

    Args:
        tool_name: Name of the tool to execute
        arguments: Arguments to pass to the tool
        tool_functions: Dictionary of available tool functions
        user_id: User ID for cache key generation
        organization_id: Tenant org ID for cache key isolation

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

        # Check cache for cacheable tools
        cached_result = None
        cache_key = None

        if (CACHE_AVAILABLE and cache and cache._enabled and
            tool_name in CACHEABLE_TOOLS and
            tool_name not in NON_CACHEABLE_TOOLS):

            cache_key = cache._generate_key(
                f"tool:{tool_name}",
                f"org:{organization_id or 0}:{user_id or 'default'}",
                **arguments
            )
            cached_result = await cache.get(cache_key)

            if cached_result is not None:
                tool_call.result = cached_result
                tool_call.execution_time_ms = (time.time() - start_time) * 1000
                logger.info(f"Tool {tool_name} CACHE HIT in {tool_call.execution_time_ms:.1f}ms")

                # Record cache hit metric
                if METRICS_AVAILABLE and cache_metrics:
                    cache_metrics.record(tool_name, hit=True, execution_time_ms=tool_call.execution_time_ms)

                return tool_call

        # Execute the tool (handle both sync and async)
        if asyncio.iscoroutinefunction(func):
            result = await func(arguments)
        else:
            result = func(arguments)

        tool_call.result = result
        tool_call.execution_time_ms = (time.time() - start_time) * 1000

        # Cache the result for cacheable tools
        if (cache_key and result is not None and
            "error" not in result):
            ttl = CACHEABLE_TOOLS.get(tool_name, 300)
            await cache.set(cache_key, result, ttl)
            logger.info(f"Tool {tool_name} executed in {tool_call.execution_time_ms:.1f}ms (cached for {ttl}s)")
        else:
            logger.info(f"Tool {tool_name} executed in {tool_call.execution_time_ms:.1f}ms")

        # Record cache miss metric (actual execution)
        if METRICS_AVAILABLE and cache_metrics:
            cache_metrics.record(tool_name, hit=False, execution_time_ms=tool_call.execution_time_ms)

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

    # Get extracted entities from pattern matching (e.g., borrower names)
    extracted_entities = state.get("extracted_entities", {})

    # Map entities to tool arguments based on tool type
    if tool_name == "search_loans":
        # Priority: extracted_entities.search_query > entities.loan_ids > entities.borrower_names
        if extracted_entities.get("search_query"):
            args["query"] = extracted_entities["search_query"]
            logger.info(f"[GATHER] search_loans using extracted search_query: {args['query']}")
        elif extracted_entities.get("borrower_name"):
            args["query"] = extracted_entities["borrower_name"]
            logger.info(f"[GATHER] search_loans using extracted borrower_name: {args['query']}")
        elif entities.get("loan_ids"):
            args["query"] = entities["loan_ids"][0]
        elif entities.get("borrower_names"):
            args["query"] = entities["borrower_names"][0]
            logger.info(f"[GATHER] search_loans using entity borrower_name: {args['query']}")
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

    # Communication tools
    elif tool_name in ["click_to_dial", "make_call", "call_contact"]:
        # Get phone number from entities or extracted_entities
        phone = None
        if entities.get("phone_numbers"):
            phone = entities["phone_numbers"][0]
        elif state.get("extracted_entities", {}).get("phone_number"):
            phone = state["extracted_entities"]["phone_number"]

        if phone:
            args["phone_number"] = phone
            args["contact_name"] = entities.get("borrower_names", ["Contact"])[0] if entities.get("borrower_names") else "Contact"

    elif tool_name in ["send_sms", "send_text", "text_contact"]:
        # Get phone number from entities or extracted_entities
        phone = None
        if entities.get("phone_numbers"):
            phone = entities["phone_numbers"][0]
        elif state.get("extracted_entities", {}).get("phone_number"):
            phone = state["extracted_entities"]["phone_number"]

        if phone:
            args["phone_number"] = phone
            # Default message if not specified
            args["message"] = state.get("message_content", "Hello from your loan officer!")

    elif tool_name == "send_email":
        # Get email address from entities or extracted_entities
        email = None
        if entities.get("email_addresses"):
            email = entities["email_addresses"][0]
        elif state.get("extracted_entities", {}).get("email_address"):
            email = state["extracted_entities"]["email_address"]

        # Try to extract email from user message if not in entities
        if not email:
            user_message = state.get("user_message", "")
            import re
            email_match = re.search(r'[\w\.\-\+]+@[\w\.\-]+\.\w+', user_message)
            if email_match:
                email = email_match.group()

        if email:
            args["to_email"] = email
            # Default subject and body - will be enhanced by AI
            args["subject"] = state.get("email_subject", "Message from your Loan Officer")
            args["body"] = state.get("email_body", state.get("user_message", "Hello!"))
            # Pass user_id for OAuth token lookup
            args["user_id"] = state.get("user_id")

        logger.info(f"[GATHER] send_email args: {args}")

    elif tool_name == "get_top_leads":
        # Extract limit from query (e.g., "top 3 leads" -> limit=3)
        user_message = state.get("user_message", "").lower()
        import re
        match = re.search(r"top\s*(\d+)", user_message)
        if match:
            args["limit"] = int(match.group(1))
        else:
            args["limit"] = 5  # Default to top 5
        args["require_phone"] = True  # Always require phone for calling

    elif tool_name == "get_stale_leads":
        # Extract days threshold from query (e.g., "not contacted in 7 days" -> 7)
        user_message = state.get("user_message", "").lower()
        import re
        match = re.search(r"(\d+)\s*days?", user_message)
        if match:
            args["days_threshold"] = int(match.group(1))
        else:
            args["days_threshold"] = 7  # Default to 7 days
        args["limit"] = 20
        args["include_never_contacted"] = True

    elif tool_name == "lead_status_insights":
        # No arguments needed
        pass

    elif tool_name == "get_leads_by_status":
        # Extract status from entities if available
        entities = state.get("query_entities", {})
        if entities.get("stages"):
            args["status"] = entities["stages"][0]
        args["limit"] = 25

    return args


async def gather_data(
    state: AgentState,
    tool_functions: Dict[str, Callable] = None
) -> AgentState:
    """
    Execute required tools in parallel for 3-5x speedup.

    This node executes ALL tools concurrently using asyncio.gather(),
    reducing sequential execution time (e.g., 15s -> 3-5s).

    Args:
        state: Current agent state with required_tools populated
        tool_functions: Dictionary mapping tool names to their implementations

    Returns:
        Updated state with gathered data
    """
    state = add_node_trace(state, "gather")
    start_time = time.time()

    if tool_functions is None:
        tool_functions = {}

    # Debug: Log available tools
    available_tool_names = list(tool_functions.keys())
    logger.info(f"[GATHER] Available tool functions: {available_tool_names}")

    required_tools = state.get("required_tools", [])
    logger.info(f"[GATHER] Required tools from analyzer: {required_tools}")

    # Check if required_tools is explicitly empty list (e.g., for greetings)
    # vs None/missing (which would need a default)
    if state.get("required_tools") is None:
        logger.warning("[GATHER] No tools specified (None), using default pipeline summary")
        required_tools = ["get_pipeline"]
    elif len(required_tools) == 0:
        # Empty list means intentionally no tools needed (e.g., greeting)
        logger.info("[GATHER] Empty tools list - skipping tool execution (greeting/simple query)")
        return update_state(state, {
            "gathered_data": {},
            "data_quality": "not_needed",
            "tools_executed": [],
            "tools_errored": [],
        })

    tool_calls = []
    gathered_data = {}
    missing_data = []

    try:
        # Build list of tool execution tasks - filter out unavailable tools first
        tasks = []
        task_tool_names = []

        # Get user_id and organization_id for cache key generation
        user_id = state.get("user_id")
        organization_id = state.get("organization_id")

        for tool_name in required_tools:
            if tool_name not in tool_functions:
                logger.warning(f"[GATHER] Tool {tool_name} not available, skipping")
                missing_data.append(f"Tool not available: {tool_name}")
                continue

            args = determine_tool_arguments(tool_name, state)
            logger.info(f"[GATHER] Queuing tool {tool_name} with args: {args}")
            tasks.append(execute_tool(tool_name, args, tool_functions, user_id, organization_id))
            task_tool_names.append(tool_name)

        # Execute ALL tools in parallel for maximum speed
        # This is the key optimization: 15s sequential -> 3-5s parallel
        if tasks:
            logger.info(f"[GATHER] Executing {len(tasks)} tools in parallel...")
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Process results
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    tool_name = task_tool_names[i] if i < len(task_tool_names) else "unknown"
                    logger.error(f"[GATHER] Tool {tool_name} raised exception: {result}")
                    missing_data.append(f"{tool_name}: {str(result)}")
                    continue

                tool_calls.append(result)

                # Consolidate results into gathered_data
                if result.result is not None:
                    gathered_data[result.tool_name] = result.result
                elif result.error:
                    missing_data.append(f"{result.tool_name}: {result.error}")

        # Calculate execution time
        execution_time = (time.time() - start_time) * 1000

        # Assess data quality
        total_tools = len(required_tools)
        successful_tools = len([tc for tc in tool_calls if tc.result is not None])

        if successful_tools == 0:
            data_quality = "insufficient"
        elif successful_tools < total_tools * 0.5:
            data_quality = "partial"
        else:
            data_quality = "complete"

        # Update state with results
        state = update_state(state, {
            "tool_calls": tool_calls,
            "gathered_data": gathered_data,
            "data_quality": data_quality,
            "missing_data": missing_data
        })

        logger.info(
            f"[GATHER] Complete: {successful_tools}/{total_tools} tools succeeded "
            f"in {execution_time:.0f}ms (parallel execution)"
        )

        # Log gathered data summary
        for key, val in gathered_data.items():
            if isinstance(val, dict):
                logger.debug(f"[GATHER] {key}: {len(val)} keys")
            elif isinstance(val, list):
                logger.debug(f"[GATHER] {key}: {len(val)} items")

        return state

    except Exception as e:
        logger.error(f"Data gathering failed: {e}", exc_info=True)
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
