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

logger = logging.getLogger(__name__)


# Intent to scoped tools mapping (matches analyze.py)
INTENT_TO_SCOPED_TOOLS = {
    # Fast response intents (use Haiku, minimal tools)
    "greeting": [],  # No tools needed for greetings
    "simple": ["get_daily_priorities"],  # Minimal tools for simple queries
    # Standard intents (use Sonnet, appropriate tools)
    "priorities": ["get_daily_priorities", "get_tasks", "get_pipeline"],
    "tasks": ["get_tasks", "create_task", "get_daily_priorities"],
    "leads": ["lead_status_insights", "get_leads_by_status", "get_top_leads", "get_stale_leads", "search_leads"],
    "top_leads": ["get_top_leads"],  # Specific entry for "call my top leads" queries
    "pipeline": ["get_pipeline", "get_pipeline_metrics", "search_loans"],
    "historical": ["get_performance_by_period", "compare_periods", "get_data_availability"],  # Q3 vs Q4, period comparisons
    "rates": ["get_rate_lock_advisory", "get_pipeline"],
    "calls": ["click_to_dial", "make_call", "call_contact", "get_top_leads", "search_leads"],
    "email": ["get_emails_needing_response", "send_email", "search_email_inbox", "search_leads", "search_loans", "create_referral_partner"],
    "schedule": ["get_tasks", "get_daily_priorities"],
    "documents": ["search_loans", "get_pipeline"],
    "compliance": ["search_loans", "get_pipeline"],
    "sla": ["get_pipeline", "get_pipeline_metrics"],
    "reports": ["get_pipeline_metrics", "get_pipeline"],
    "coaching": ["get_pipeline_metrics", "get_pipeline", "lead_status_insights"],
    "customer": ["search_leads", "search_loans"],
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

        def should_skip_reasoning(state: AgentState) -> Literal["reason", "respond"]:
            """Determine if reasoning can be skipped for simple queries."""
            query_complexity = state.get("query_complexity", "moderate")
            data_quality = state.get("data_quality", "complete")

            if query_complexity == "simple" and data_quality == "complete":
                gathered_data = state.get("gathered_data", {})
                if len(gathered_data) <= 1:
                    return "respond"
            return "reason"

        # Define edges
        workflow.set_entry_point("analyze")
        workflow.add_edge("analyze", "gather")

        workflow.add_conditional_edges(
            "gather",
            should_skip_reasoning,
            {"reason": "reason", "respond": "respond"}
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

    Returns:
        Response dictionary with text, metadata, and optional structured data
    """
    import time
    from .intent_router import classify_intent, INTENT_TO_AGENTS

    start_time = datetime.utcnow()
    start_perf = time.perf_counter()
    timing = {}  # Detailed timing breakdown

    logger.info(f"[ORCHESTRATOR] ========================================")
    logger.info(f"[ORCHESTRATOR] START | Query: '{message[:80]}{'...' if len(message) > 80 else ''}'")
    logger.info(f"[ORCHESTRATOR] ========================================")

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
            logger.warning(f"[ORCHESTRATOR] No organization_id for user {user_id} — tenant isolation degraded")

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
        state = update_state(state, {
            "intent_agents": intent_agents,
            "intent_confidence": intent_confidence,
            "pre_classified_intent": intent,
            "pre_classified_method": intent_method,
        })
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
        # STEP 3: Execute workflow
        # ================================================================
        step_start = time.perf_counter()
        final_state = await orchestrator.ainvoke(state)
        timing["workflow_execute"] = (time.perf_counter() - step_start) * 1000

        # ================================================================
        # STEP 4: Build response
        # ================================================================
        step_start = time.perf_counter()
        processing_time = (datetime.utcnow() - start_time).total_seconds()

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
        # HALLUCINATION VERIFICATION (Background - non-blocking)
        # ================================================================
        # Run hallucination check in background to not delay response
        verification_enabled = os.getenv("ENABLE_HALLUCINATION_VERIFICATION", "true").lower() == "true"
        if verification_enabled and final_state.get("response") and final_state.get("gathered_data"):
            try:
                # Fire and forget - verification runs asynchronously
                asyncio.create_task(
                    _verify_response_hallucinations(
                        session_id=conversation_id or state.get("session_id"),
                        message_id=f"msg_{datetime.utcnow().timestamp()}",
                        response_text=final_state.get("response", ""),
                        gathered_data=final_state.get("gathered_data", {}),
                        tools_used=[tc.tool_name for tc in final_state.get("tool_calls", [])],
                        user_id=user_id,
                        db_session=db_session
                    )
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
        logger.info(f"[ORCHESTRATOR] END | {processing_time:.2f}s total")
        logger.info(f"[ORCHESTRATOR] ========================================")

        return response

    except Exception as e:
        processing_time = (datetime.utcnow() - start_time).total_seconds()
        logger.error(f"[ORCHESTRATOR] FAILED after {processing_time:.2f}s: {e}", exc_info=True)
        return {
            "response": f"I apologize, but I encountered an error processing your request. Please try again.",
            "error": "Internal server error",
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

        self.conversation_id = f"conv_{user_id}_{datetime.utcnow().timestamp()}"
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
            "timestamp": datetime.utcnow().isoformat()
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
            "timestamp": datetime.utcnow().isoformat()
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
) -> None:
    """
    Verify an AI response for hallucinations and record metrics.

    This function runs in the background after the response is sent to the user.
    It extracts claims from the response, verifies them against source data,
    and records the results to the metrics database.

    Args:
        session_id: Session/conversation identifier
        message_id: Unique message identifier
        response_text: The AI response to verify
        gathered_data: Tool outputs used to generate the response
        tools_used: List of tool names that were called
        user_id: User ID for metrics recording
        db_session: Database session for recording metrics (optional)
        use_llm: Whether to use LLM for extraction/verification (default True)
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

    except Exception as e:
        logger.error(f"[HALLUCINATION] Verification failed for message {message_id}: {e}")
