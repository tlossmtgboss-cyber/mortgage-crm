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

# Tenant isolation context for registry tools
try:
    from ..tools.base import set_tenant_context, clear_tenant_context
    TENANT_CONTEXT_AVAILABLE = True
except ImportError:
    set_tenant_context = lambda org_id: None
    clear_tenant_context = lambda: None
    TENANT_CONTEXT_AVAILABLE = False

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

# Import tool argument validator
try:
    from agents.tool_validator import validate_tool_arguments
    VALIDATOR_AVAILABLE = True
except ImportError:
    validate_tool_arguments = None
    VALIDATOR_AVAILABLE = False

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

# Tools that need LLM-composed content before execution.
# These are deferred from gather to the execute phase so the LLM can
# compose proper content (e.g., email subject/body) in reason_and_respond.
DEFERRED_TO_EXECUTE_TOOLS = {
    "send_email",  # LLM must compose subject + body before sending
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

        # Validate tool arguments before execution
        if VALIDATOR_AVAILABLE and validate_tool_arguments is not None:
            is_valid, arguments, val_errors = validate_tool_arguments(tool_name, arguments)
            if not is_valid:
                tool_call.error = f"Argument validation failed: {'; '.join(val_errors)}"
                tool_call.execution_time_ms = (time.time() - start_time) * 1000
                logger.warning(f"[GATHER] Tool {tool_name} args invalid: {val_errors}")
                return tool_call
            # Use sanitized arguments going forward
            tool_call.arguments = arguments

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

            # Stampede protection: set a short-lived lock to prevent
            # concurrent identical requests from all executing the same tool.
            # If another request is already computing this, wait for its result.
            stampede_lock_key = f"lock:{cache_key}"
            try:
                lock_acquired = await cache.set(stampede_lock_key, "1", ttl=30, nx=True)
                if not lock_acquired:
                    # Another request is computing — brief wait then retry cache
                    import asyncio as _asyncio
                    for _ in range(3):
                        await _asyncio.sleep(0.5)
                        cached_result = await cache.get(cache_key)
                        if cached_result is not None:
                            tool_call.result = cached_result
                            tool_call.execution_time_ms = (time.time() - start_time) * 1000
                            logger.info(f"Tool {tool_name} CACHE HIT (after stampede wait)")
                            return tool_call
                    # Timed out waiting — proceed with execution
            except Exception:
                pass  # Redis lock failed — proceed without stampede protection

        # Set tenant context before executing any registry tool.
        # This ensures execute_query() can validate results against the org boundary.
        if organization_id is not None:
            set_tenant_context(organization_id)

        # Execute the tool (handle both sync and async) with timeout.
        # IMPORTANT: ContextVars do NOT propagate to ThreadPoolExecutor threads.
        # For sync tools, we use copy_context().run() to propagate the tenant
        # context into the executor thread. Without this, get_tenant_context()
        # returns None in the thread and tenant isolation is bypassed.
        TOOL_TIMEOUT = 10  # seconds (reduced from 15s for faster failure)
        try:
            try:
                if asyncio.iscoroutinefunction(func):
                    result = await asyncio.wait_for(func(arguments), timeout=TOOL_TIMEOUT)
                else:
                    from contextvars import copy_context
                    ctx = copy_context()
                    loop = asyncio.get_event_loop()
                    result = await asyncio.wait_for(
                        loop.run_in_executor(None, ctx.run, func, arguments), timeout=TOOL_TIMEOUT
                    )
            except asyncio.TimeoutError:
                tool_call.error = f"Tool '{tool_name}' timed out after {TOOL_TIMEOUT}s"
                tool_call.execution_time_ms = (time.time() - start_time) * 1000
                logger.error(f"Tool {tool_name} timed out after {TOOL_TIMEOUT}s")
                return tool_call

            # Normalize tool result: ToolResult dataclass -> dict
            if hasattr(result, 'to_dict'):
                result = result.to_dict()
            elif not isinstance(result, dict):
                result = {"result": result}

            tool_call.result = result
            tool_call.execution_time_ms = (time.time() - start_time) * 1000

            # Cache the result for cacheable tools and release stampede lock
            if (cache_key and result is not None and
                isinstance(result, dict) and "error" not in result):
                ttl = CACHEABLE_TOOLS.get(tool_name, 300)
                await cache.set(cache_key, result, ttl)
                # Release stampede lock
                try:
                    await cache.delete(f"lock:{cache_key}")
                except Exception:
                    pass
                logger.info(f"Tool {tool_name} executed in {tool_call.execution_time_ms:.1f}ms (cached for {ttl}s)")
            else:
                logger.info(f"Tool {tool_name} executed in {tool_call.execution_time_ms:.1f}ms")
        finally:
            if organization_id is not None:
                clear_tenant_context()

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

    When the user is viewing a specific lead/loan in the CRM UI,
    active_lead_id/active_loan_id are set and used to resolve
    ambiguous references like "send them an email" or "create a task".

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

    # Active entity context from CRM UI (the lead/loan the user is viewing)
    active_lead_id = state.get("active_lead_id")
    active_loan_id = state.get("active_loan_id")
    active_entity_data = state.get("active_entity_data") or {}

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
        # Link task to the active lead/loan when the user is viewing one
        if active_lead_id:
            args["lead_id"] = str(active_lead_id)
        if active_loan_id:
            args["loan_id"] = str(active_loan_id)

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

        # Fall back to active entity email when user says "send them an email"
        if not email and active_entity_data:
            email = active_entity_data.get("lead_email") or active_entity_data.get("loan_borrower_email")
            if email:
                logger.info(f"[GATHER] send_email resolved email from active entity context")

        if email:
            args["to_email"] = email
            # Default subject and body - will be enhanced by AI
            args["subject"] = state.get("email_subject", "Message from your Loan Officer")
            args["body"] = state.get("email_body", state.get("user_message", "Hello!"))
            # Pass user_id for OAuth token lookup
            args["user_id"] = state.get("user_id")
            # Link to active entity for tracking
            if active_lead_id:
                args["contact_id"] = str(active_lead_id)
                args["contact_type"] = "lead"

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


def _fetch_active_entity_data(
    active_lead_id: Optional[int],
    active_loan_id: Optional[int],
) -> dict:
    """
    Fetch details for the lead/loan the user is currently viewing in the CRM.

    This gives the AI real context so it can answer questions like
    "send them an email" or "what stage is this loan at?" accurately.

    Returns a dict with keyed data (lead_* and/or loan_*), or empty dict.
    """
    from ..tools.base import execute_query, execute_single
    result = {}

    if active_lead_id:
        try:
            lead = execute_single(
                """SELECT l.id, l.first_name, l.last_name, l.email, l.phone,
                          l.status, l.source, l.created_at,
                          l.estimated_loan_amount, l.credit_score_range,
                          l.property_type_interest, l.timeline, l.notes,
                          l.last_contact_date, l.next_followup_date, l.lead_score,
                          lo.name as assigned_lo_name
                   FROM leads l
                   LEFT JOIN loan_officers lo ON l.assigned_to = lo.id
                   WHERE l.id = :lead_id""",
                {"lead_id": active_lead_id}
            )
            if lead:
                result["lead_id"] = active_lead_id
                result["lead_name"] = f"{lead.get('first_name', '')} {lead.get('last_name', '')}".strip()
                result["lead_email"] = lead.get("email")
                result["lead_phone"] = lead.get("phone")
                result["lead_status"] = lead.get("status")
                result["lead_source"] = lead.get("source")
                result["lead_score"] = lead.get("lead_score")
                result["lead_loan_amount"] = lead.get("estimated_loan_amount")
                result["lead_credit_range"] = lead.get("credit_score_range")
                result["lead_last_contact"] = str(lead.get("last_contact_date")) if lead.get("last_contact_date") else None
                result["lead_next_followup"] = str(lead.get("next_followup_date")) if lead.get("next_followup_date") else None
                result["lead_assigned_to"] = lead.get("assigned_lo_name")
                result["lead_notes"] = lead.get("notes")
                logger.info(f"[GATHER] Fetched active lead context: {result['lead_name']} (id={active_lead_id})")
        except Exception as e:
            logger.warning(f"[GATHER] Failed to fetch active lead {active_lead_id}: {e}")

    if active_loan_id:
        try:
            loan = execute_single(
                """SELECT ln.id, ln.loan_number, ln.borrower_name, ln.borrower_email,
                          ln.loan_amount, ln.loan_type, ln.interest_rate, ln.stage,
                          ln.property_address, ln.closing_date, ln.lock_expiration_date,
                          ln.created_at, ln.updated_at,
                          lo.name as assigned_lo_name
                   FROM loans ln
                   LEFT JOIN loan_officers lo ON ln.loan_officer_id = lo.id
                   WHERE ln.id = :loan_id""",
                {"loan_id": active_loan_id}
            )
            if loan:
                result["loan_id"] = active_loan_id
                result["loan_number"] = loan.get("loan_number")
                result["loan_borrower_name"] = loan.get("borrower_name")
                result["loan_borrower_email"] = loan.get("borrower_email")
                result["loan_amount"] = loan.get("loan_amount")
                result["loan_type"] = loan.get("loan_type")
                result["loan_rate"] = loan.get("interest_rate")
                result["loan_stage"] = loan.get("stage")
                result["loan_property"] = loan.get("property_address")
                result["loan_closing_date"] = str(loan.get("closing_date")) if loan.get("closing_date") else None
                result["loan_lock_expiration"] = str(loan.get("lock_expiration_date")) if loan.get("lock_expiration_date") else None
                result["loan_assigned_to"] = loan.get("assigned_lo_name")
                logger.info(f"[GATHER] Fetched active loan context: {result.get('loan_borrower_name', '')} (id={active_loan_id})")
        except Exception as e:
            logger.warning(f"[GATHER] Failed to fetch active loan {active_loan_id}: {e}")

    return result


async def gather_data(
    state: AgentState,
    tool_functions: Dict[str, Callable] = None
) -> AgentState:
    """
    Execute required tools in parallel for 3-5x speedup.

    This node executes ALL tools concurrently using asyncio.gather(),
    reducing sequential execution time (e.g., 15s -> 3-5s).

    When the user is viewing a specific lead/loan in the CRM, the active
    entity's details are auto-fetched and injected into gathered_data so
    the LLM has real context for answers and action execution.

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

    # ================================================================
    # AUTO-FETCH ACTIVE ENTITY DATA (lead/loan user is viewing in CRM)
    # ================================================================
    active_lead_id = state.get("active_lead_id")
    active_loan_id = state.get("active_loan_id")
    organization_id = state.get("organization_id")

    if active_lead_id or active_loan_id:
        try:
            # Set tenant context so execute_query applies org isolation
            if organization_id is not None:
                set_tenant_context(organization_id)
            try:
                entity_data = _fetch_active_entity_data(active_lead_id, active_loan_id)
            finally:
                if organization_id is not None:
                    clear_tenant_context()

            if entity_data:
                state = update_state(state, {"active_entity_data": entity_data})
                logger.info(f"[GATHER] Active entity context loaded: lead_id={active_lead_id}, loan_id={active_loan_id}")
        except Exception as e:
            logger.warning(f"[GATHER] Active entity fetch failed (non-blocking): {e}")

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
    deferred_actions = []  # Tools deferred to execute phase (need LLM content)

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

            # Defer tools that need LLM-composed content (e.g., send_email).
            # These will be executed in the execute phase after reason_and_respond
            # composes the content.
            if tool_name in DEFERRED_TO_EXECUTE_TOOLS:
                logger.info(f"[GATHER] Deferring {tool_name} to execute phase (needs LLM content). Args: {args}")
                deferred_actions.append({
                    "type": tool_name,
                    "params": args,
                    "auto_execute": True,
                    "deferred_from_gather": True,
                })
                # Store the recipient info so the LLM knows who the email is for
                gathered_data[tool_name] = {
                    "status": "deferred",
                    "message": f"Email to {args.get('to_email', 'recipient')} will be sent after composing content.",
                    "to_email": args.get("to_email"),
                    "user_request": state.get("user_message", ""),
                }
                continue

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

        # Inject active entity data into gathered_data so the LLM sees it
        active_entity_data = state.get("active_entity_data")
        if active_entity_data:
            gathered_data["active_crm_context"] = active_entity_data
            # If no other tools succeeded but we have entity context, upgrade quality
            if data_quality == "insufficient" and active_entity_data:
                data_quality = "partial"

        # Update state with results
        state_updates = {
            "tool_calls": tool_calls,
            "gathered_data": gathered_data,
            "data_quality": data_quality,
            "missing_data": missing_data,
        }

        # Pass deferred actions to execute phase
        if deferred_actions:
            state_updates["deferred_actions"] = deferred_actions
            # Ensure execute node runs even if requires_action wasn't set
            state_updates["requires_action"] = True
            logger.info(f"[GATHER] {len(deferred_actions)} actions deferred to execute phase")

        state = update_state(state, state_updates)

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

        # Fire cross-agent events based on gathered tool results (fire-and-forget).
        # This catches compliance checks, doc expiration, lead scoring, etc. that
        # run as data-gathering (read) operations, not as write actions in execute.
        if gathered_data:
            asyncio.ensure_future(
                _emit_gather_cross_agent_events(gathered_data, state)
            )

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

    PII is masked before formatting to prevent sensitive data (SSNs,
    account numbers, full phone numbers) from being sent to the LLM API.

    Args:
        state: Agent state with gathered_data populated

    Returns:
        Formatted string of all gathered data
    """
    gathered_data = state.get("gathered_data", {})
    if not gathered_data:
        return "No data was gathered."

    # Mask PII before formatting (import from reason_and_respond to avoid duplication)
    try:
        from .reason_and_respond import _mask_gathered_data
        masked_data = _mask_gathered_data(gathered_data)
    except ImportError:
        masked_data = gathered_data

    sections = []

    for tool_name, data in masked_data.items():
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


# =============================================================================
# Cross-agent event emission from gather results
# =============================================================================

async def _emit_gather_cross_agent_events(
    gathered_data: Dict[str, Any],
    state: AgentState,
) -> None:
    """Inspect gathered tool results and emit inter-agent events.

    Runs as a fire-and-forget coroutine after the gather node completes.
    Any failure is logged and swallowed -- it never blocks the response.
    """
    try:
        from services.agent_event_bridge import agent_event_bridge
    except ImportError:
        return  # Bridge not available

    org_id = str(state.get("organization_id")) if state.get("organization_id") else None

    for tool_name, result in gathered_data.items():
        if not isinstance(result, dict):
            continue

        try:
            # check_document_expiration -> expired documents
            if tool_name == "check_document_expiration" and result.get("expired"):
                expired_docs = result.get("expired", [])
                loan_ids_seen = set()
                for doc in expired_docs:
                    lid = doc.get("loan_id")
                    if lid and lid not in loan_ids_seen:
                        loan_ids_seen.add(lid)
                        types = [d.get("document_type", "unknown") for d in expired_docs if d.get("loan_id") == lid]
                        await agent_event_bridge.on_documents_expired(
                            loan_id=lid,
                            doc_types=types,
                            org_id=org_id,
                        )

            # score_lead -> hot lead detection
            if tool_name == "score_lead" and result.get("new_score", 0) >= 60:
                await agent_event_bridge.on_hot_lead_detected(
                    lead_id=result.get("lead_id"),
                    score=result.get("new_score", 0),
                    lo_id=result.get("lo_id"),
                    org_id=org_id,
                )

            # check_trid_compliance -> compliance violation
            if tool_name in ("check_trid_compliance", "check_tolerance_violations", "audit_loan_file"):
                issues = result.get("issues", [])
                violations = result.get("violations", [])
                failed_checks = result.get("results", {}).get("failed", []) if isinstance(result.get("results"), dict) else []
                for issue in issues + violations + failed_checks:
                    severity = issue.get("severity", "medium")
                    if severity in ("high", "critical"):
                        await agent_event_bridge.on_compliance_violation(
                            loan_id=result.get("loan_id"),
                            violation_type=issue.get("type", tool_name),
                            severity=severity,
                            description=issue.get("message", ""),
                            org_id=org_id,
                        )

            # get_bottleneck_analysis -> stalled stages
            if tool_name == "get_bottleneck_analysis":
                for bottleneck in result.get("bottlenecks", []):
                    if bottleneck.get("severity") == "critical":
                        await agent_event_bridge.on_loan_stalled(
                            loan_id=0,  # Aggregate signal
                            days_stale=int(bottleneck.get("avg_days", 0)),
                            stage=bottleneck.get("stage", "UNKNOWN"),
                            org_id=org_id,
                        )

            # get_loan_aging_report -> stalled loans by stage
            if tool_name == "get_loan_aging_report":
                for stage_info in result.get("by_stage", []):
                    if stage_info.get("over_threshold", 0) > 0 and stage_info.get("avg_days", 0) > 14:
                        await agent_event_bridge.on_loan_stalled(
                            loan_id=0,
                            days_stale=int(stage_info.get("avg_days", 0)),
                            stage=stage_info.get("stage", "UNKNOWN"),
                            org_id=org_id,
                        )

        except Exception as e:
            logger.warning(
                "[GATHER] Cross-agent event emission failed for %s: %s",
                tool_name, e,
            )
