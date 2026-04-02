"""
LangGraph Orchestrator

This module creates and manages the LangGraph workflow that coordinates
all the agent nodes for processing user queries.

OPTIMIZATION v3: Intent-Based Tool Loading
- Analyze node classifies intent using fast pattern matching (~1-5ms)
- Only 8-16 tools loaded per request instead of all 160
- Tool loading happens dynamically based on intent from analyze step
"""

import asyncio
import logging
import os
from typing import Any, Callable, Dict, Optional, Literal
from datetime import datetime

from langgraph.graph import StateGraph, END
from anthropic import Anthropic

from .state import (
    AgentState,
    QueryIntent,
    create_initial_state,
    update_state,
    add_node_trace
)
from .nodes.analyze import analyze_query
from .nodes.gather import gather_data
from .nodes.reason import reason_and_analyze
from .nodes.execute import execute_actions
from .nodes.respond import generate_response, format_structured_response
from .nodes.reason_and_respond import reason_and_respond
from .hallucination_verifier import get_hallucination_verifier

# Enterprise modules: budget, rate limiting, audit, correlation IDs
from .token_budget import get_token_budget, get_rate_limiter
from .audit import AuditEntry, get_audit_logger, set_request_id, get_request_id, clear_request_id

logger = logging.getLogger(__name__)


def _is_retryable(error: Exception) -> bool:
    """Check if error is transient and worth retrying."""
    error_str = str(error).lower()
    return any(keyword in error_str for keyword in [
        'rate_limit', 'timeout', '429', '503', 'overloaded',
        'internal_error', 'connection', 'temporarily'
    ])


# =============================================================================
# POST-RESPONSE MEMORY EXTRACTION
# =============================================================================

import re as _re

# Patterns for detecting user preferences and facts (lightweight, no LLM call)
_PREFERENCE_PATTERNS = [
    # Explicit preferences
    (_re.compile(r"(?:i\s+)?prefer\s+(.{5,80})", _re.IGNORECASE), "preference"),
    (_re.compile(r"(?:please\s+)?always\s+(.{5,80})", _re.IGNORECASE), "directive"),
    (_re.compile(r"(?:please\s+)?never\s+(.{5,80})", _re.IGNORECASE), "directive"),
    (_re.compile(r"don'?t\s+(?:ever\s+)?(?:send|show|give|email|text|call)\s+me\s+(.{5,80})", _re.IGNORECASE), "directive"),
    (_re.compile(r"(?:i\s+)?(?:only\s+)?want\s+(?:to\s+see|to\s+get|to\s+receive)\s+(.{5,80})", _re.IGNORECASE), "preference"),
    (_re.compile(r"(?:i\s+)?(?:like|love)\s+(?:when|it\s+when|seeing)\s+(.{5,80})", _re.IGNORECASE), "preference"),
    # Key facts
    (_re.compile(r"my\s+credit\s+score\s+is\s+(\d{3})", _re.IGNORECASE), "fact"),
    (_re.compile(r"i(?:'m|\s+am)\s+looking\s+(?:at|for|to\s+buy)\s+(.{5,80})", _re.IGNORECASE), "fact"),
    (_re.compile(r"my\s+(?:target|goal)\s+(?:is|:)\s+(.{5,80})", _re.IGNORECASE), "fact"),
    (_re.compile(r"i\s+(?:work|specialize)\s+(?:in|with|on)\s+(.{5,80})", _re.IGNORECASE), "fact"),
    (_re.compile(r"my\s+(?:average|typical)\s+(?:loan|deal)\s+(?:size|amount)\s+is\s+(.{5,80})", _re.IGNORECASE), "fact"),
    (_re.compile(r"i\s+(?:mainly|mostly|primarily)\s+(?:do|handle|work\s+on)\s+(.{5,80})", _re.IGNORECASE), "fact"),
]

# Confidence levels by extraction type
_MEMORY_CONFIDENCE = {
    "directive": 0.9,   # Explicit user instruction
    "preference": 0.7,  # Auto-extracted preference
    "fact": 0.7,        # Auto-extracted fact
    "context": 0.6,     # Situational context
}

# TTL in days by memory type (None = no expiry)
_MEMORY_TTL_DAYS = {
    "preference": None,  # Preferences don't expire
    "directive": None,   # Directives don't expire
    "fact": 90,          # Facts expire in 90 days
    "context": 30,       # Context expires in 30 days
}


def _extract_and_save_memories(
    final_state: dict,
    db_session=None,
) -> None:
    """
    Extract user preferences and facts from the conversation and save
    to the AgentMemory table. Uses lightweight regex/pattern matching,
    NOT an LLM call.

    Gracefully degrades: logs and continues on any failure.

    Args:
        final_state: The completed orchestrator state
        db_session: SQLAlchemy session (if None, creates its own)
    """
    try:
        user_message = final_state.get("user_message", "")
        user_id = final_state.get("user_id", "")
        organization_id = final_state.get("organization_id")

        if not user_message or not user_id:
            return

        # Scan user message for preference/fact patterns
        extracted = []
        for pattern, mem_type in _PREFERENCE_PATTERNS:
            match = pattern.search(user_message)
            if match:
                captured = match.group(1).strip().rstrip(".,!?")
                if len(captured) >= 5:  # Skip trivially short matches
                    extracted.append({
                        "type": mem_type,
                        "key": f"auto_{mem_type}_{len(extracted)}",
                        "value": captured[:255],
                        "confidence": _MEMORY_CONFIDENCE.get(mem_type, 0.6),
                    })

        if not extracted:
            return

        # Lazy imports to avoid circular dependencies
        from datetime import datetime, timezone, timedelta
        from database.models.agent_memory import AgentMemory, MemoryType

        _type_map = {
            "preference": MemoryType.PREFERENCE,
            "directive": MemoryType.DIRECTIVE,
            "fact": MemoryType.FACT,
            "context": MemoryType.CONTEXT,
        }

        # Use provided session or create a new one
        own_session = False
        session = db_session
        if session is None:
            from db import SessionLocal
            session = SessionLocal()
            own_session = True

        try:
            now = datetime.now(timezone.utc)
            saved_count = 0

            for item in extracted:
                ttl_days = _MEMORY_TTL_DAYS.get(item["type"])
                expires_at = (now + timedelta(days=ttl_days)) if ttl_days else None

                memory = AgentMemory(
                    user_id=int(user_id) if str(user_id).isdigit() else user_id,
                    organization_id=organization_id,
                    memory_type=_type_map.get(item["type"], MemoryType.FACT),
                    key=item["key"],
                    value=item["value"],
                    confidence=item["confidence"],
                    agent_role="orchestrator",
                    created_at=now,
                    updated_at=now,
                    expires_at=expires_at,
                )
                session.add(memory)
                saved_count += 1

            session.commit()
            logger.info(
                f"[ORCHESTRATOR] Saved {saved_count} memories for user {user_id}: "
                f"{[e['type'] + ':' + e['value'][:30] for e in extracted]}"
            )

        except Exception as e:
            logger.warning(f"[ORCHESTRATOR] Memory save failed (graceful degradation): {e}")
            try:
                session.rollback()
            except Exception:
                pass
        finally:
            if own_session:
                session.close()

    except Exception as e:
        logger.warning(f"[ORCHESTRATOR] Memory extraction failed (graceful degradation): {e}")


# Intent to scoped tools mapping (matches analyze.py)
INTENT_TO_SCOPED_TOOLS = {
    # Fast response intents (use Haiku, minimal tools)
    "greeting": [],  # No tools needed for greetings
    "simple": ["get_daily_priorities"],  # Minimal tools for simple queries
    # Standard intents (use Sonnet, appropriate tools)
    "priorities": ["get_daily_priorities", "get_tasks", "get_pipeline"],
    "tasks": ["get_tasks", "create_task", "get_daily_priorities", "get_task_queue", "update_task_status", "assign_task", "get_task_templates", "bulk_update_tasks", "execute_workflow", "get_workflow_status", "get_daily_call_list"],
    "leads": ["lead_status_insights", "get_leads_by_status", "get_top_leads", "get_stale_leads", "search_leads"],
    "top_leads": ["get_top_leads", "score_lead", "suggest_followup", "get_lead_details"],
    "pipeline": ["get_pipeline", "get_pipeline_metrics", "search_loans"],
    "historical": ["get_performance_by_period", "compare_periods", "get_data_availability"],  # Q3 vs Q4, period comparisons
    "rates": ["get_current_rates", "recommend_lock_strategy", "compare_rate_scenarios", "monitor_float_position", "get_market_events", "calculate_lock_cost", "get_extension_pricing", "analyze_rate_trends", "get_rate_lock_advisory", "get_pipeline"],
    "calls": ["click_to_dial", "make_call", "call_contact", "get_top_leads", "search_leads"],
    "email": ["get_emails_needing_response", "send_email", "search_email_inbox", "search_leads", "search_loans", "create_referral_partner"],
    "schedule": ["get_availability", "book_appointment", "reschedule_appointment", "cancel_appointment", "get_upcoming_appointments", "send_appointment_reminder", "sync_external_calendar", "optimize_schedule"],
    "documents": ["get_missing_documents", "get_loan_conditions", "track_document_request", "send_document_reminder", "check_document_expiration", "get_third_party_status", "get_document_timeline", "escalate_issue", "search_loans"],
    "compliance": ["check_trid_compliance", "check_respa_compliance", "check_fair_lending", "get_state_requirements", "audit_loan_file", "get_disclosure_timeline", "check_tolerance_violations", "get_compliance_history", "search_loans"],
    "sla": ["check_sla_status", "get_sla_dashboard", "get_sla_alerts", "calculate_stage_sla", "get_sla_report", "project_sla_breach", "escalate_sla_breach", "get_pipeline", "get_pipeline_metrics"],
    "reports": ["generate_pipeline_report", "generate_production_report", "get_report_templates", "schedule_report", "export_report", "get_dashboard_metrics", "get_performance_by_period", "compare_periods", "get_pipeline_metrics", "get_pipeline"],
    "coaching": ["get_lo_metrics", "compare_to_peers", "identify_training_needs", "generate_coaching_plan", "track_improvement", "get_best_practices", "get_performance_trends", "set_performance_goals", "get_performance_by_period", "compare_periods", "get_data_availability", "get_pipeline_metrics"],
    "customer": ["get_customer_360", "map_relationships", "calculate_ltv", "assess_churn_risk", "find_opportunities", "get_interaction_history", "get_referral_network", "search_leads", "search_loans"],
    "video": ["schedule_video_meeting", "get_meeting_recordings", "analyze_meeting", "send_async_video", "get_video_analytics", "extract_meeting_action_items", "generate_meeting_summary", "get_participant_insights"],
    "integrations": ["sync_los_data", "check_integration_status", "trigger_credit_pull", "submit_to_aus", "order_appraisal", "order_title", "get_pricing_engine_quote", "send_for_esign"],
    "billing": ["get_subscription_status", "get_plans", "change_plan", "get_billing_history", "update_payment_method", "get_usage_metrics", "manage_addons", "pause_subscription"],
    "onboarding": ["get_onboarding_status", "get_checklist", "complete_step", "start_guided_tour", "get_training_resources", "get_setup_wizard", "request_support", "track_progress"],
    "notifications": ["send_notification", "get_pending_notifications", "get_notification_templates", "schedule_notification", "get_delivery_status", "update_preferences", "get_preferences", "batch_send"],
    "profit": ["calculate_loan_profitability", "analyze_margins_by_segment", "forecast_revenue", "compare_lo_profitability", "optimize_pricing", "get_cost_breakdown", "calculate_pull_through_impact", "get_profitability_trends"],
    "operations": ["get_pipeline_metrics", "get_loan_aging_report", "get_bottleneck_analysis", "check_sla_status", "get_sla_dashboard", "escalate_sla_breach", "get_lo_pipeline_breakdown", "get_compliance_history"],
    "compound": ["get_pipeline_metrics", "search_loans", "search_leads", "get_tasks", "create_task", "send_email", "schedule_followup"],
    "content_marketing": ["get_pipeline_metrics", "search_leads", "draft_message"],
    "general": ["get_daily_priorities", "get_pipeline", "get_tasks"],
}


def create_orchestrator(
    tool_functions: Dict[str, Callable] = None,
    anthropic_client: Anthropic = None,
    autonomous_mode: bool = True,
    use_unified_mode: bool = True  # New flag to enable optimized mode
) -> StateGraph:
    """
    Create the LangGraph orchestrator workflow.

    OPTIMIZED workflow (use_unified_mode=True, default):
    1. ANALYZE -> Classify query, extract entities, determine tools
    2. GATHER -> Execute tools and collect data
    3. REASON_AND_RESPOND -> Unified analysis + response (1 LLM call)
    4. EXECUTE -> Optional: Perform actions if requested

    LEGACY workflow (use_unified_mode=False):
    1. ANALYZE -> Classify query, extract entities, determine tools
    2. GATHER -> Execute tools and collect data
    3. REASON -> Analyze data, generate insights
    4. EXECUTE -> Perform actions if requested
    5. RESPOND -> Generate final response

    Args:
        tool_functions: Dictionary mapping tool names to functions
        anthropic_client: Pre-configured Anthropic client
        autonomous_mode: Whether to auto-execute low-risk actions
        use_unified_mode: Use optimized single LLM call for reason+respond (saves ~5-7s)

    Returns:
        Compiled LangGraph StateGraph
    """

    if anthropic_client is None:
        anthropic_client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    if tool_functions is None:
        tool_functions = {}

    # Create node wrapper functions that pass dependencies
    async def analyze_node(state: AgentState) -> AgentState:
        """Query analysis node"""
        return await analyze_query(state, anthropic_client)

    async def gather_node(state: AgentState) -> AgentState:
        """Data gathering node"""
        return await gather_data(state, tool_functions)

    async def reason_node(state: AgentState) -> AgentState:
        """Reasoning node (legacy)"""
        return await reason_and_analyze(state, anthropic_client)

    async def execute_node(state: AgentState) -> AgentState:
        """Action execution node"""
        return await execute_actions(state, tool_functions, autonomous_mode)

    async def respond_node(state: AgentState) -> AgentState:
        """Response generation node (legacy)"""
        return await generate_response(state, anthropic_client)

    async def unified_reason_respond_node(state: AgentState) -> AgentState:
        """Unified reasoning + response node (optimized - saves ~5-7s)"""
        return await reason_and_respond(state, anthropic_client)

    # Build the graph
    workflow = StateGraph(AgentState)

    if use_unified_mode:
        # OPTIMIZED: Unified mode - 2 LLM calls instead of 3
        logger.info("[ORCHESTRATOR] Using UNIFIED mode (reason+respond combined)")

        # Add nodes
        workflow.add_node("analyze", analyze_node)
        workflow.add_node("gather", gather_node)
        workflow.add_node("reason_and_respond", unified_reason_respond_node)
        workflow.add_node("execute", execute_node)

        # Define routing logic for unified mode
        def should_execute_after_unified(state: AgentState) -> Literal["execute", "end"]:
            """Determine if we should execute actions after unified response."""
            requires_action = state.get("requires_action", False)
            query_intent = state.get("query_intent", QueryIntent.GENERAL_QUERY)

            if requires_action or query_intent == QueryIntent.ACTION_REQUEST:
                return "execute"
            return "end"

        # Define edges - simplified flow
        workflow.set_entry_point("analyze")
        workflow.add_edge("analyze", "gather")
        workflow.add_edge("gather", "reason_and_respond")

        # After unified node, check if we need to execute actions
        workflow.add_conditional_edges(
            "reason_and_respond",
            should_execute_after_unified,
            {
                "execute": "execute",
                "end": END
            }
        )

        # Execute leads to end (response already generated)
        workflow.add_edge("execute", END)

    else:
        # LEGACY: Separate reason and respond nodes - 3 LLM calls
        logger.info("[ORCHESTRATOR] Using LEGACY mode (separate reason + respond)")

        # Add nodes
        workflow.add_node("analyze", analyze_node)
        workflow.add_node("gather", gather_node)
        workflow.add_node("reason", reason_node)
        workflow.add_node("execute", execute_node)
        workflow.add_node("respond", respond_node)

        # Define routing logic
        def should_execute_actions(state: AgentState) -> Literal["execute", "respond"]:
            """Determine if we should execute actions or go straight to response."""
            requires_action = state.get("requires_action", False)
            query_intent = state.get("query_intent", QueryIntent.GENERAL_QUERY)

            if requires_action or query_intent == QueryIntent.ACTION_REQUEST:
                return "execute"
            return "respond"

        def should_skip_reasoning(state: AgentState) -> Literal["reason", "execute_check"]:
            """Determine if reasoning can be skipped for simple queries.
            Always routes to execute_check (not respond) to ensure actions are never skipped."""
            query_complexity = state.get("query_complexity", "moderate")
            data_quality = state.get("data_quality", "complete")

            if query_complexity == "simple" and data_quality == "complete":
                gathered_data = state.get("gathered_data", {})
                if len(gathered_data) <= 1:
                    return "execute_check"
            return "reason"

        # Define edges — execute node is ALWAYS reachable
        workflow.set_entry_point("analyze")
        workflow.add_edge("analyze", "gather")

        workflow.add_conditional_edges(
            "gather",
            should_skip_reasoning,
            {"reason": "reason", "execute_check": "execute"}
        )

        workflow.add_conditional_edges(
            "reason",
            should_execute_actions,
            {"execute": "execute", "respond": "respond"}
        )

        workflow.add_edge("execute", "respond")
        workflow.add_edge("respond", END)

    # Compile the graph
    return workflow.compile()


async def run_orchestrator(
    message: str,
    user_id: str,
    user_email: str,
    user_role: str = "loan_officer",
    organization_id: Optional[int] = None,
    tool_functions: Dict[str, Callable] = None,
    anthropic_client: Anthropic = None,
    autonomous_mode: bool = True,
    conversation_id: Optional[str] = None,
    conversation_history: Optional[list] = None,
    return_structured: bool = False,
    db_session = None,
    current_user = None,
    document_context: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run the full orchestrator pipeline on a user message.

    TIMING OPTIMIZATION v4 - Two-Phase Tool Loading:
    1. PHASE 1: Quick intent classification (~1-5ms pattern, ~500ms Haiku)
    2. PHASE 2: Load only scoped tools for classified intent (8-16 tools)
    3. Execute pipeline with scoped tools

    Performance:
    - Before: 29s (load 160 tools → LLM picks → execute)
    - After: 5s (classify → load 8-16 tools → LLM picks → execute)

    Args:
        message: User's input message
        user_id: Authenticated user ID
        user_email: User's email address
        user_role: User's role in the system
        tool_functions: Available tool functions (optional, will scope dynamically)
        anthropic_client: Pre-configured Anthropic client
        autonomous_mode: Whether to auto-execute actions
        conversation_id: Optional conversation ID for multi-turn
        conversation_history: Previous conversation messages
        return_structured: Whether to return structured response
        db_session: Database session for dynamic tool loading
        current_user: Current user for dynamic tool loading
        document_context: Optional text from a user-uploaded document

    Returns:
        Response dictionary with text, metadata, and optional structured data
    """
    import time
    from .intent_router import classify_intent, INTENT_TO_AGENTS

    start_time = datetime.now(timezone.utc)
    start_perf = time.perf_counter()
    timing = {}  # Detailed timing breakdown

    # Assign correlation ID for cross-service tracing
    request_id = set_request_id(conversation_id)

    logger.info(f"[ORCHESTRATOR] ========================================")
    logger.info(f"[ORCHESTRATOR] START | rid={request_id} | Query: '{message[:80]}{'...' if len(message) > 80 else ''}'")
    logger.info(f"[ORCHESTRATOR] ========================================")

    # Resolve org_id early for budget/rate checks
    _early_org_id = organization_id
    if _early_org_id is None and current_user is not None:
        _early_org_id = getattr(current_user, 'organization_id', None)

    # ================================================================
    # ENTERPRISE GATE: Rate limiting + token budget check
    # ================================================================
    if _early_org_id is not None:
        # Rate limit check
        rate_limiter = get_rate_limiter()
        allowed, retry_after = rate_limiter.check_rate_limit(_early_org_id)
        if not allowed:
            clear_request_id()
            return {
                "response": "You're sending requests too quickly. Please wait a moment and try again.",
                "error": "rate_limited",
                "error_type": "rate_limit",
                "retry_after_seconds": retry_after,
                "processing_time_seconds": 0,
            }

        # Token budget check
        budget = get_token_budget()
        if not budget.check_budget(_early_org_id):
            clear_request_id()
            return {
                "response": "AI usage limit reached for this period. Please try again later or contact your administrator.",
                "error": "budget_exceeded",
                "error_type": "budget",
                "processing_time_seconds": 0,
            }

    try:
        # ================================================================
        # PHASE 1: Quick Intent Classification (BEFORE loading tools)
        # ================================================================
        step_start = time.perf_counter()
        intent_result = await classify_intent(message, anthropic_client)
        timing["intent_classify"] = (time.perf_counter() - step_start) * 1000

        intent = intent_result["intent"]
        intent_confidence = intent_result["confidence"]
        intent_agents = intent_result["agents"]
        intent_method = intent_result["method"]

        logger.info(
            f"[ORCHESTRATOR] PHASE 1 - Intent: {intent} | "
            f"confidence={intent_confidence:.2f} | method={intent_method} | "
            f"agents={intent_agents} | time={timing['intent_classify']:.1f}ms"
        )

        # ================================================================
        # PHASE 2: Load ONLY scoped tools for this intent
        # ================================================================
        step_start = time.perf_counter()

        # Get scoped tools based on intent
        scoped_tool_names = INTENT_TO_SCOPED_TOOLS.get(intent, INTENT_TO_SCOPED_TOOLS["general"])

        # If tool_functions provided, filter to scoped tools
        # If db_session and current_user provided, create scoped tools dynamically
        if tool_functions:
            # Filter existing tools to only scoped ones
            scoped_tools = {
                name: func for name, func in tool_functions.items()
                if name in scoped_tool_names
            }
            # Always include base tools that might be needed
            for name in ["get_pipeline", "get_tasks", "search_leads", "search_loans"]:
                if name in tool_functions and name not in scoped_tools:
                    scoped_tools[name] = tool_functions[name]
        elif db_session and current_user:
            # Dynamic tool loading based on intent
            from .dynamic_tool_loader import create_scoped_tools
            scoped_tools = create_scoped_tools(db_session, current_user, intent)
        else:
            # Fallback to provided tools or empty
            scoped_tools = tool_functions or {}

        # Warn and fall back if no tools available for this intent
        if not scoped_tools and tool_functions:
            logger.warning(f"[ORCHESTRATOR] No tools available for intent '{intent}' — falling back to all provided tools")
            scoped_tools = tool_functions

        timing["load_tools"] = (time.perf_counter() - step_start) * 1000
        tool_count = len(scoped_tools)

        logger.info(
            f"[ORCHESTRATOR] PHASE 2 - Loaded {tool_count} scoped tools: "
            f"{list(scoped_tools.keys())} | time={timing['load_tools']:.1f}ms"
        )

        # ================================================================
        # STEP 3: Create initial state (with intent pre-populated)
        # ================================================================
        step_start = time.perf_counter()
        # Resolve organization_id from current_user if not explicitly provided
        resolved_org_id = organization_id
        if resolved_org_id is None and current_user is not None:
            resolved_org_id = getattr(current_user, 'organization_id', None)

        if resolved_org_id is None:
            logger.error(f"[ORCHESTRATOR] No organization_id for user {user_id} — tenant isolation BLOCKED")
            return {
                "response": "Unable to process your request. Your account is missing organization context. Please contact support.",
                "error": "tenant_isolation_failed",
                "error_type": "authorization",
                "processing_time_seconds": (datetime.now(timezone.utc) - start_time).total_seconds()
            }

        state = create_initial_state(
            user_message=message,
            user_id=user_id,
            user_email=user_email,
            user_role=user_role,
            organization_id=resolved_org_id,
            conversation_id=conversation_id,
            conversation_history=conversation_history
        )
        # Pre-populate intent info so analyze node can skip re-classification
        # when confidence is high enough (>0.90)
        state_updates = {
            "intent_agents": intent_agents,
            "intent_confidence": intent_confidence,
            "pre_classified_intent": intent,
            "pre_classified_method": intent_method,
        }
        # Inject document context if provided (one-shot, not saved to memory)
        if document_context:
            state_updates["document_context"] = document_context
        state = update_state(state, state_updates)
        timing["init_state"] = (time.perf_counter() - step_start) * 1000

        # ================================================================
        # STEP 4: Create orchestrator graph with scoped tools
        # ================================================================
        step_start = time.perf_counter()
        orchestrator = create_orchestrator(
            tool_functions=scoped_tools,  # Use scoped tools, not all tools
            anthropic_client=anthropic_client,
            autonomous_mode=autonomous_mode
        )
        timing["create_graph"] = (time.perf_counter() - step_start) * 1000

        logger.info(f"[ORCHESTRATOR] Graph created with {tool_count} scoped tools")

        # ================================================================
        # STEP 3: Execute workflow (with retry on transient LLM failures)
        # ================================================================
        step_start = time.perf_counter()
        MAX_RETRIES = 2
        for attempt in range(MAX_RETRIES + 1):
            try:
                final_state = await orchestrator.ainvoke(state)
                break
            except Exception as workflow_err:
                if attempt < MAX_RETRIES and _is_retryable(workflow_err):
                    wait_time = (2 ** attempt) * 0.5  # 0.5s, 1s
                    logger.warning(f"[ORCHESTRATOR] LLM retry {attempt + 1}/{MAX_RETRIES} after {wait_time}s: {workflow_err}")
                    await asyncio.sleep(wait_time)
                    continue
                raise
        timing["workflow_execute"] = (time.perf_counter() - step_start) * 1000

        # ================================================================
        # STEP 4: Build response
        # ================================================================
        step_start = time.perf_counter()
        processing_time = (datetime.now(timezone.utc) - start_time).total_seconds()

        response = {
            "response": final_state.get("response", ""),
            "intent": final_state.get("query_intent", QueryIntent.GENERAL_QUERY).value,
            "confidence": final_state.get("confidence_score", 0.5),
            "follow_up_suggestions": final_state.get("follow_up_suggestions", []),
            "processing_time_seconds": processing_time,
            "data_quality": final_state.get("data_quality", "unknown"),
            "actions_executed": [
                {
                    "type": a.action_type,
                    "success": a.success,
                    "message": a.message
                }
                for a in final_state.get("actions_executed", [])
            ],
            "actions_pending": final_state.get("actions_pending", []),
            # Add performance metrics
            "performance": {
                "analysis_method": final_state.get("analysis_method", "unknown"),
                "intent_agents": final_state.get("intent_agents", []),
                "tools_used": [tc.tool_name for tc in final_state.get("tool_calls", [])],
                "tool_count": tool_count,
            }
        }
        timing["build_response"] = (time.perf_counter() - step_start) * 1000

        if return_structured:
            response["structured"] = format_structured_response(final_state)

        # Log any errors that occurred
        errors = final_state.get("errors", [])
        if errors:
            logger.warning(f"Orchestrator completed with errors: {errors}")
            response["warnings"] = errors

        # ================================================================
        # MEMORY EXTRACTION — save user preferences/facts from conversation
        # ================================================================
        try:
            _extract_and_save_memories(final_state, db_session)
        except Exception as mem_err:
            logger.warning(f"[ORCHESTRATOR] Post-response memory extraction failed: {mem_err}")

        # ================================================================
        # AUDIT LOGGING — structured compliance trail with token tracking
        # ================================================================
        total_tokens_used = 0
        try:
            # Extract actual token usage from the LLM response stored in state
            tokens_input = final_state.get("tokens_input", 0)
            tokens_output = final_state.get("tokens_output", 0)
            total_tokens_used = tokens_input + tokens_output

            # Record token usage for budget tracking
            if resolved_org_id is not None and total_tokens_used > 0:
                get_token_budget().record_usage(resolved_org_id, total_tokens_used)

            tool_calls = final_state.get("tool_calls", [])
            audit_entry = AuditEntry(
                request_id=request_id,
                user_id=user_id,
                organization_id=resolved_org_id,
                intent=intent or "chat",
                user_message=str(message)[:2000],
                response_text=str(response.get("response", ""))[:2000],
                model_used=final_state.get("model_used", "anthropic"),
                tokens_input=tokens_input,
                tokens_output=tokens_output,
                tools_called=[tc.tool_name for tc in tool_calls],
                tool_results_summary={
                    tc.tool_name: "ok" if tc.result else (tc.error or "no_result")
                    for tc in tool_calls
                },
                actions_executed=[
                    {"type": a.action_type, "success": a.success}
                    for a in final_state.get("actions_executed", [])
                ],
                actions_pending=[
                    a.get("type", "unknown")
                    for a in final_state.get("actions_pending", [])
                ],
                processing_time_ms=processing_time * 1000,
                data_quality=final_state.get("data_quality", "unknown"),
                errors=errors,
            )
            get_audit_logger().log(audit_entry, db_session)
        except Exception as audit_err:
            logger.warning(f"Failed to log AI audit: {audit_err}")

        # Add token usage to performance metrics
        response["performance"]["tokens_input"] = tokens_input if 'tokens_input' in dir() else 0
        response["performance"]["tokens_output"] = tokens_output if 'tokens_output' in dir() else 0
        response["performance"]["tokens_total"] = total_tokens_used

        # ================================================================
        # HALLUCINATION VERIFICATION
        # Blocking for compliance-sensitive intents, background for others
        # ================================================================
        BLOCKING_VERIFICATION_INTENTS = {"compliance", "rates", "sla"}
        verification_enabled = os.getenv("ENABLE_HALLUCINATION_VERIFICATION", "true").lower() == "true"
        verification_timeout = int(os.getenv("HALLUCINATION_VERIFICATION_TIMEOUT", "30"))
        if verification_enabled and final_state.get("response") and final_state.get("gathered_data"):
            try:
                async def _run_verification_task():
                    """Run hallucination verification."""
                    return await _verify_response_hallucinations(
                        session_id=conversation_id or state.get("session_id"),
                        message_id=f"msg_{datetime.now(timezone.utc).timestamp()}",
                        response_text=final_state.get("response", ""),
                        gathered_data=final_state.get("gathered_data", {}),
                        tools_used=[tc.tool_name for tc in final_state.get("tool_calls", [])],
                        user_id=user_id,
                        db_session=db_session
                    )

                if intent in BLOCKING_VERIFICATION_INTENTS:
                    # Blocking mode for compliance-sensitive intents
                    try:
                        verification = await asyncio.wait_for(
                            _run_verification_task(), timeout=10.0
                        )
                        if verification and hasattr(verification, 'faithfulness_score') and verification.faithfulness_score < 0.7:
                            response["response"] += "\n\nThis response may need human verification for accuracy."
                            logger.warning(f"[HALLUCINATION] Low faithfulness ({verification.faithfulness_score:.2%}) for compliance intent '{intent}'")
                    except asyncio.TimeoutError:
                        logger.warning("[HALLUCINATION] Blocking hallucination check timed out after 10s")
                    except Exception as verify_err:
                        logger.warning(f"[HALLUCINATION] Blocking verification failed: {verify_err}")
                else:
                    # Non-blocking for general queries
                    async def _run_verification_with_timeout():
                        """Wrapper with timeout and error handling for background verification."""
                        try:
                            await asyncio.wait_for(_run_verification_task(), timeout=verification_timeout)
                        except asyncio.TimeoutError:
                            logger.warning(f"[HALLUCINATION] Verification timed out after {verification_timeout}s")
                        except Exception as verify_err:
                            logger.error(f"[HALLUCINATION] Background verification failed: {verify_err}", exc_info=True)

                    task = asyncio.create_task(_run_verification_with_timeout())
                    task.add_done_callback(
                        lambda t: logger.error(f"[HALLUCINATION] Task error: {t.exception()}", exc_info=t.exception())
                        if t.exception() else None
                    )
                    logger.debug("[ORCHESTRATOR] Hallucination verification started in background")
            except Exception as e:
                logger.warning(f"[ORCHESTRATOR] Failed to start hallucination verification: {e}")

        # ================================================================
        # TIMING SUMMARY
        # ================================================================
        total_perf = (time.perf_counter() - start_perf) * 1000
        node_trace = final_state.get("node_trace", [])

        # Add intent routing info to performance metrics
        response["performance"]["intent_method"] = intent_method
        response["performance"]["intent_classify_ms"] = timing["intent_classify"]
        response["performance"]["scoped_tool_names"] = scoped_tool_names

        logger.info(f"[ORCHESTRATOR] ========================================")
        logger.info(f"[ORCHESTRATOR] ⏱️ TIMING BREAKDOWN (v4 - Two-Phase):")
        logger.info(f"  PHASE 1 - Intent Classification:")
        logger.info(f"    - intent_classify:  {timing['intent_classify']:>8.1f}ms ({intent_method})")
        logger.info(f"  PHASE 2 - Scoped Tool Loading:")
        logger.info(f"    - load_tools:       {timing['load_tools']:>8.1f}ms ({tool_count} tools)")
        logger.info(f"  Pipeline Execution:")
        logger.info(f"    - init_state:       {timing['init_state']:>8.1f}ms")
        logger.info(f"    - create_graph:     {timing['create_graph']:>8.1f}ms")
        logger.info(f"    - workflow_execute: {timing['workflow_execute']:>8.1f}ms")
        logger.info(f"    - build_response:   {timing['build_response']:>8.1f}ms")
        logger.info(f"  ────────────────────────────────")
        logger.info(f"  TOTAL:                {total_perf:>8.1f}ms ({processing_time:.2f}s)")
        logger.info(f"[ORCHESTRATOR] ----------------------------------------")
        logger.info(f"[ORCHESTRATOR] Intent: {intent} → Agents: {intent_agents}")
        logger.info(f"[ORCHESTRATOR] Scoped tools: {list(scoped_tools.keys())}")
        logger.info(f"[ORCHESTRATOR] Tools used: {len(final_state.get('tool_calls', []))} of {tool_count} available")
        logger.info(f"[ORCHESTRATOR] ========================================")
        logger.info(f"[ORCHESTRATOR] END | rid={request_id} | {processing_time:.2f}s total")
        logger.info(f"[ORCHESTRATOR] ========================================")

        response["request_id"] = request_id
        clear_request_id()

        return response

    except Exception as e:
        processing_time = (datetime.now(timezone.utc) - start_time).total_seconds()
        rid = get_request_id() or "unknown"
        logger.error(f"[ORCHESTRATOR] FAILED rid={rid} after {processing_time:.2f}s: {e}", exc_info=True)

        # Classify error type for client-side handling and graceful degradation
        error_type = "internal"
        error_msg = "I apologize, but I encountered an error processing your request. Please try again."

        err_name = type(e).__name__
        err_str = str(e).lower()

        if "RateLimitError" in err_name or "429" in err_str:
            error_type = "external_api_rate_limit"
            error_msg = "The AI service is experiencing high demand. Please try again in a moment."
        elif "AuthenticationError" in err_name or "401" in err_str:
            error_type = "external_api_auth"
            error_msg = "AI service authentication error. Please contact your administrator."
        elif "Anthropic" in err_name or "APIError" in err_name:
            error_type = "external_api"
            error_msg = "The AI service is temporarily unavailable. Please try again in a moment."
        elif "Timeout" in err_name or "TimeoutError" in err_name:
            error_type = "timeout"
            error_msg = "The request took too long to process. Please try a simpler query."
        elif "SQLAlchemy" in err_name or "OperationalError" in err_name:
            error_type = "database"
            error_msg = "A database error occurred. Please try again."
        elif "ConnectionError" in err_name or "connection" in err_str:
            error_type = "connection"
            error_msg = "Unable to reach the AI service. Please check your connection and try again."

        # Audit the failure
        try:
            if db_session and _early_org_id:
                failure_entry = AuditEntry(
                    request_id=rid,
                    user_id=user_id,
                    organization_id=_early_org_id,
                    intent="error",
                    user_message=str(message)[:2000],
                    response_text=error_msg,
                    model_used="n/a",
                    errors=[f"{error_type}: {str(e)[:500]}"],
                    processing_time_ms=processing_time * 1000,
                )
                get_audit_logger().log(failure_entry, db_session)
        except Exception:
            pass

        clear_request_id()

        return {
            "response": error_msg,
            "error": "Internal server error",
            "error_type": error_type,
            "request_id": rid,
            "processing_time_seconds": processing_time
        }


class OrchestratorSession:
    """
    Manages a conversational session with the orchestrator.

    Maintains conversation history and context across multiple turns.
    """

    def __init__(
        self,
        user_id: str,
        user_email: str,
        user_role: str = "loan_officer",
        organization_id: Optional[int] = None,
        tool_functions: Dict[str, Callable] = None,
        anthropic_client: Anthropic = None,
        autonomous_mode: bool = True
    ):
        self.user_id = user_id
        self.user_email = user_email
        self.user_role = user_role
        self.organization_id = organization_id
        self.tool_functions = tool_functions or {}
        self.anthropic_client = anthropic_client
        self.autonomous_mode = autonomous_mode

        self.conversation_id = f"conv_{user_id}_{datetime.now(timezone.utc).timestamp()}"
        self.conversation_history = []
        self.turn_count = 0

    async def chat(self, message: str) -> Dict[str, Any]:
        """
        Process a message in the conversation.

        Args:
            message: User's message

        Returns:
            Response dictionary
        """
        self.turn_count += 1

        # Add user message to history
        self.conversation_history.append({
            "role": "user",
            "content": message,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

        # Run orchestrator
        response = await run_orchestrator(
            message=message,
            user_id=self.user_id,
            user_email=self.user_email,
            user_role=self.user_role,
            organization_id=self.organization_id,
            tool_functions=self.tool_functions,
            anthropic_client=self.anthropic_client,
            autonomous_mode=self.autonomous_mode,
            conversation_id=self.conversation_id,
            conversation_history=self.conversation_history[-10:]  # Last 10 turns
        )

        # Add assistant response to history
        self.conversation_history.append({
            "role": "assistant",
            "content": response.get("response", ""),
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

        response["turn_number"] = self.turn_count
        response["conversation_id"] = self.conversation_id

        return response

    def get_history(self) -> list:
        """Get the full conversation history."""
        return self.conversation_history

    def clear_history(self):
        """Clear conversation history."""
        self.conversation_history = []
        self.turn_count = 0


# =============================================================================
# HALLUCINATION VERIFICATION HELPER
# =============================================================================

async def _verify_response_hallucinations(
    session_id: str,
    message_id: str,
    response_text: str,
    gathered_data: Dict[str, Any],
    tools_used: list,
    user_id: str,
    db_session = None,
    use_llm: bool = True
) -> Optional[Any]:
    """
    Verify an AI response for hallucinations and record metrics.

    Returns the HallucinationReport so callers (especially blocking mode for
    compliance-sensitive intents) can inspect faithfulness_score and act on it.

    Args:
        session_id: Session/conversation identifier
        message_id: Unique message identifier
        response_text: The AI response to verify
        gathered_data: Tool outputs used to generate the response
        tools_used: List of tool names that were called
        user_id: User ID for metrics recording
        db_session: Database session for recording metrics (optional)
        use_llm: Whether to use LLM for extraction/verification (default True)

    Returns:
        HallucinationReport with faithfulness_score, or None on failure
    """
    try:
        logger.info(f"[HALLUCINATION] Starting verification for message {message_id}")

        # Get the hallucination verifier
        verifier = get_hallucination_verifier()

        # Generate the hallucination report
        report = await verifier.generate_report(
            session_id=session_id or "unknown",
            message_id=message_id,
            response_text=response_text,
            source_data=gathered_data,
            tools_used=tools_used,
            use_llm=use_llm
        )

        logger.info(
            f"[HALLUCINATION] Verification complete for {message_id}: "
            f"faithfulness={report.faithfulness_score:.2%}, "
            f"claims={report.total_claims} "
            f"(verified={report.verified_claims}, "
            f"unsupported={report.unsupported_claims}, "
            f"contradicted={report.contradicted_claims}), "
            f"time={report.analysis_time_ms:.0f}ms"
        )

        # Log warnings for potential hallucinations
        if report.contradicted_claims > 0:
            logger.warning(
                f"[HALLUCINATION] ⚠️ Found {report.contradicted_claims} contradicted claims "
                f"in message {message_id}"
            )
            for result in report.verification_results:
                if result.status.value == "contradicted":
                    logger.warning(
                        f"[HALLUCINATION] - Contradicted: '{result.claim_text[:100]}...' "
                        f"(expected: {result.expected_value}, claimed: {result.claimed_value})"
                    )

        # Record metrics to database if session provided
        if db_session is not None:
            try:
                from .metrics.service import AIMetricsService

                # Convert user_id to int if string
                uid = int(user_id) if isinstance(user_id, str) and user_id.isdigit() else 0

                await AIMetricsService.record_hallucination_report(
                    db=db_session,
                    user_id=uid,
                    report=report
                )
                logger.debug(f"[HALLUCINATION] Metrics recorded for message {message_id}")
            except Exception as metrics_error:
                logger.warning(f"[HALLUCINATION] Failed to record metrics: {metrics_error}")

        return report

    except Exception as e:
        logger.error(f"[HALLUCINATION] Verification failed for message {message_id}: {e}")
        return None
