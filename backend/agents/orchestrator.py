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
import threading
import time as _time_module
from typing import Any, Callable, Dict, Optional, Literal
from datetime import datetime, timezone
from enum import Enum

from langgraph.graph import StateGraph, END
from anthropic import Anthropic

from .anthropic_client import get_anthropic_client

from .state import (
    AgentState,
    QueryIntent,
    create_initial_state,
    update_state,
    add_node_trace
)
from .nodes.analyze import analyze_query
from .nodes.gather import gather_data
from .nodes.execute import execute_actions
from .nodes.reason_and_respond import reason_and_respond
from .nodes.respond import format_structured_response
from .hallucination_verifier import get_hallucination_verifier
from .orchestration.quality_analyzer import QualityAnalyzer
from .checkpointer import get_checkpointer

# Enterprise modules: budget, rate limiting, audit, correlation IDs
from .token_budget import get_token_budget, get_rate_limiter
from .audit import AuditEntry, get_audit_logger, set_request_id, get_request_id, clear_request_id

logger = logging.getLogger(__name__)


# =============================================================================
# CIRCUIT BREAKER
# =============================================================================

class CircuitState(Enum):
    CLOSED = "closed"          # Normal operation — requests flow through
    OPEN = "open"              # Failing — reject requests immediately
    HALF_OPEN = "half_open"    # Testing recovery — allow one probe request


class CircuitBreaker:
    """
    Thread-safe circuit breaker for LLM API calls.

    Prevents cascading failures during Anthropic outages by fast-failing
    requests instead of letting each one timeout individually.

    State transitions:
        CLOSED  -> OPEN:      after `failure_threshold` consecutive failures
        OPEN    -> HALF_OPEN: after `cooldown_seconds` elapse
        HALF_OPEN -> CLOSED:  if the probe request succeeds
        HALF_OPEN -> OPEN:    if the probe request fails
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        cooldown_seconds: float = 30.0,
        name: str = "llm",
    ):
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.name = name

        self._state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._last_failure_time: float = 0.0
        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            if self._state == CircuitState.OPEN:
                # Check if cooldown has elapsed -> transition to HALF_OPEN
                elapsed = _time_module.monotonic() - self._last_failure_time
                if elapsed >= self.cooldown_seconds:
                    self._state = CircuitState.HALF_OPEN
                    logger.warning(
                        f"[CIRCUIT-BREAKER:{self.name}] OPEN -> HALF_OPEN "
                        f"(cooldown {self.cooldown_seconds}s elapsed)"
                    )
            return self._state

    def allow_request(self) -> bool:
        """Return True if the request should be allowed through."""
        current = self.state  # triggers OPEN->HALF_OPEN check
        if current == CircuitState.CLOSED:
            return True
        if current == CircuitState.HALF_OPEN:
            # Allow exactly one probe request
            return True
        # OPEN — reject
        return False

    def record_success(self) -> None:
        """Record a successful call — reset failure count, close circuit."""
        with self._lock:
            prev = self._state
            self._consecutive_failures = 0
            self._state = CircuitState.CLOSED
            if prev != CircuitState.CLOSED:
                logger.warning(
                    f"[CIRCUIT-BREAKER:{self.name}] {prev.value} -> CLOSED (success)"
                )

    def record_failure(self) -> None:
        """Record a failed call — increment counter, potentially open circuit."""
        with self._lock:
            self._consecutive_failures += 1
            self._last_failure_time = _time_module.monotonic()

            if self._state == CircuitState.HALF_OPEN:
                # Probe failed — go back to OPEN
                self._state = CircuitState.OPEN
                logger.warning(
                    f"[CIRCUIT-BREAKER:{self.name}] HALF_OPEN -> OPEN "
                    f"(probe request failed)"
                )
            elif (
                self._state == CircuitState.CLOSED
                and self._consecutive_failures >= self.failure_threshold
            ):
                self._state = CircuitState.OPEN
                logger.warning(
                    f"[CIRCUIT-BREAKER:{self.name}] CLOSED -> OPEN "
                    f"({self._consecutive_failures} consecutive failures)"
                )


# Module-level circuit breaker instance shared across all orchestrator calls.
# Single instance is fine — the LLM backend is the same for all requests.
_llm_circuit_breaker = CircuitBreaker(failure_threshold=5, cooldown_seconds=30.0)


def _get_circuit_breaker() -> CircuitBreaker:
    """Return the module-level circuit breaker (useful for testing)."""
    return _llm_circuit_breaker


def _is_retryable(error: Exception) -> bool:
    """Check if error is transient and worth retrying."""
    error_str = str(error).lower()
    return any(keyword in error_str for keyword in [
        'rate_limit', 'timeout', '429', '503', 'overloaded',
        'internal_error', 'connection', 'temporarily'
    ])


# Single source of truth lives in intent_router.py
from .intent_router import INTENT_TO_SCOPED_TOOLS  # noqa: F401


async def create_orchestrator(
    tool_functions: Dict[str, Callable] = None,
    anthropic_client: Anthropic = None,
    autonomous_mode: bool = True,
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
        anthropic_client = get_anthropic_client()

    if tool_functions is None:
        tool_functions = {}

    # Create node wrapper functions that pass dependencies
    async def analyze_node(state: AgentState) -> AgentState:
        """Query analysis node"""
        return await analyze_query(state, anthropic_client)

    async def gather_node(state: AgentState) -> AgentState:
        """Data gathering node"""
        return await gather_data(state, tool_functions)

    async def execute_node(state: AgentState) -> AgentState:
        """Action execution node"""
        return await execute_actions(state, tool_functions, autonomous_mode)

    async def unified_reason_respond_node(state: AgentState) -> AgentState:
        """Unified reasoning + response node (optimized - saves ~5-7s)"""
        return await reason_and_respond(state, anthropic_client)

    async def verify_and_score_node(state: AgentState) -> AgentState:
        """
        Post-response verification and quality scoring node.

        Runs hallucination verification (comparing response against gathered data)
        and quality analysis (scoring the prompt/response quality) in parallel.
        Never blocks the pipeline — failures result in missing metadata, not errors.
        """
        import time as _time
        node_start = _time.perf_counter()
        state = add_node_trace(state, "verify_and_score")

        response_text = state.get("response", "")
        gathered_data = state.get("gathered_data", {})
        tool_calls = state.get("tool_calls", [])
        tools_used = [tc.tool_name for tc in tool_calls] if tool_calls else []

        updates = {}

        # --- Hallucination Verification ---
        verification_enabled = os.getenv("ENABLE_HALLUCINATION_VERIFICATION", "true").lower() == "true"
        if verification_enabled and response_text and gathered_data:
            try:
                verifier = get_hallucination_verifier()
                # Use rule-based verification in the pipeline node to avoid
                # adding LLM latency; the full LLM-based check still runs
                # post-response (blocking for compliance intents, background
                # for others) in run_orchestrator.
                report = await verifier.generate_report(
                    session_id=state.get("conversation_id") or "pipeline",
                    message_id=f"node_{datetime.now(timezone.utc).timestamp():.0f}",
                    response_text=response_text,
                    source_data=gathered_data,
                    tools_used=tools_used,
                    use_llm=False,  # Rule-based only — fast, no extra API call
                )

                verification_summary = {
                    "faithfulness_score": report.faithfulness_score,
                    "hallucination_rate": report.hallucination_rate,
                    "total_claims": report.total_claims,
                    "verified_claims": report.verified_claims,
                    "contradicted_claims": report.contradicted_claims,
                    "unsupported_claims": report.unsupported_claims,
                    "analysis_time_ms": report.analysis_time_ms,
                }
                updates["verification_report"] = verification_summary

                # Flag if high-confidence hallucinations detected
                node_intent = state.get("intent_str", "")
                COMPLIANCE_CRITICAL_INTENTS = {"compliance", "rates", "sla"}
                if report.contradicted_claims > 0 and report.hallucination_rate > 0.3:
                    updates["verification_passed"] = False
                    logger.warning(
                        f"[VERIFY] High hallucination rate ({report.hallucination_rate:.0%}) "
                        f"— {report.contradicted_claims} contradicted claims"
                    )
                else:
                    updates["verification_passed"] = True

                # Block response delivery for compliance-critical intents
                # with low faithfulness scores
                if node_intent in COMPLIANCE_CRITICAL_INTENTS and report.faithfulness_score < 0.5:
                    updates["response"] = (
                        "I'm not confident enough in this answer to share it "
                        "— it involves compliance-sensitive information. "
                        "Please consult your compliance team or check the "
                        "guidelines directly."
                    )
                    updates["verification_passed"] = False
                    updates["blocked_by_verification"] = True
                    logger.warning(
                        f"[VERIFY] Response BLOCKED for compliance intent '{node_intent}' "
                        f"— faithfulness={report.faithfulness_score:.0%}"
                    )

                logger.info(
                    f"[VERIFY] Hallucination check: faithfulness={report.faithfulness_score:.0%}, "
                    f"claims={report.total_claims}, contradicted={report.contradicted_claims}, "
                    f"time={report.analysis_time_ms:.0f}ms"
                )
            except Exception as e:
                node_intent = state.get("intent_str", "")
                COMPLIANCE_CRITICAL_INTENTS = {"compliance", "rates", "sla"}
                if node_intent in COMPLIANCE_CRITICAL_INTENTS:
                    updates["verification_passed"] = False
                    logger.warning(f"[VERIFY] Hallucination verification failed for compliance intent '{node_intent}': {e}")
                else:
                    updates["verification_passed"] = True  # Don't block on failure for non-compliance intents
                    logger.warning(f"[VERIFY] Hallucination verification failed (graceful): {e}")

        # --- Quality Analysis ---
        try:
            analyzer = QualityAnalyzer()
            # Score the response as a proxy for quality — the analyzer is designed
            # for prompts but works on any text with role/objective language.
            quick_score = analyzer.get_quick_score(response_text)
            updates["quality_score"] = {
                "response_quality": quick_score,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            logger.info(f"[VERIFY] Quality score: {quick_score}/100")
        except Exception as e:
            logger.warning(f"[VERIFY] Quality analysis failed (graceful): {e}")

        elapsed_ms = (_time.perf_counter() - node_start) * 1000
        logger.info(f"[VERIFY] verify_and_score completed in {elapsed_ms:.1f}ms")

        if updates:
            state = update_state(state, updates)
        return state

    # Build the graph
    workflow = StateGraph(AgentState)

    # Flow: analyze → gather → reason_and_respond → route → verify_and_score|execute|END
    workflow.add_node("analyze", analyze_node)
    workflow.add_node("gather", gather_node)
    workflow.add_node("reason_and_respond", unified_reason_respond_node)
    workflow.add_node("verify_and_score", verify_and_score_node)
    workflow.add_node("execute", execute_node)

    def route_after_respond(state: AgentState) -> Literal["verify_and_score", "execute", "end"]:
        requires_action = state.get("requires_action", False)
        query_intent = state.get("query_intent", QueryIntent.GENERAL_QUERY)
        intent_str = state.get("intent_str", "")
        use_haiku = state.get("use_haiku", False)

        if requires_action or query_intent == QueryIntent.ACTION_REQUEST:
            return "execute"

        SKIP_VERIFY_INTENTS = {"greeting", "simple", "schedule", "tasks",
                               "video", "notifications", "onboarding",
                               "billing", "calls"}
        if intent_str in SKIP_VERIFY_INTENTS or use_haiku:
            return "end"

        return "verify_and_score"

    def should_execute_after_verify(state: AgentState) -> Literal["execute", "end"]:
        requires_action = state.get("requires_action", False)
        query_intent = state.get("query_intent", QueryIntent.GENERAL_QUERY)

        if requires_action or query_intent == QueryIntent.ACTION_REQUEST:
            return "execute"
        return "end"

    workflow.set_entry_point("analyze")
    workflow.add_edge("analyze", "gather")
    workflow.add_edge("gather", "reason_and_respond")

    workflow.add_conditional_edges(
        "reason_and_respond",
        route_after_respond,
        {
            "verify_and_score": "verify_and_score",
            "execute": "execute",
            "end": END
        }
    )

    workflow.add_conditional_edges(
        "verify_and_score",
        should_execute_after_verify,
        {
            "execute": "execute",
            "end": END
        }
    )

    workflow.add_edge("execute", END)

    # Compile the graph (with optional durable checkpointing)
    checkpointer = await get_checkpointer()
    return workflow.compile(checkpointer=checkpointer)


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
    active_lead_id: Optional[int] = None,
    active_loan_id: Optional[int] = None,
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

        # Dollar-cost circuit breaker check
        try:
            from services.ai_cost_tracker import check_circuit_breaker
            cb_allowed, cb_reason = check_circuit_breaker(
                org_id=_early_org_id,
                db=db_session,
                agent_type=None,  # Agent type not yet known at this point
            )
            if not cb_allowed:
                clear_request_id()
                logger.warning(
                    "AI cost circuit breaker blocked request: org=%d reason=%s",
                    _early_org_id, cb_reason,
                )
                return {
                    "response": (
                        "AI services are temporarily limited due to daily usage limits. "
                        "Please try again later or contact your administrator."
                    ),
                    "error": "budget_exceeded",
                    "error_type": "circuit_breaker",
                    "processing_time_seconds": 0,
                }
        except Exception as e:
            # Fail open — don't block on circuit breaker errors
            logger.debug("Circuit breaker check skipped: %s", e)

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
            for name in ["get_pipeline", "get_tasks", "search_leads", "search_loans", "find_contact", "send_sms"]:
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
            conversation_history=conversation_history,
            active_lead_id=active_lead_id,
            active_loan_id=active_loan_id,
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
        orchestrator = await create_orchestrator(
            tool_functions=scoped_tools,
            anthropic_client=anthropic_client,
            autonomous_mode=autonomous_mode
        )
        timing["create_graph"] = (time.perf_counter() - step_start) * 1000

        logger.info(f"[ORCHESTRATOR] Graph created with {tool_count} scoped tools")

        # ================================================================
        # STEP 3: Execute workflow (circuit breaker + retry on transient LLM failures)
        # ================================================================
        step_start = time.perf_counter()
        circuit = _get_circuit_breaker()

        # Fast-fail if circuit is OPEN (Anthropic API likely down)
        if not circuit.allow_request():
            logger.warning(
                f"[ORCHESTRATOR] Circuit breaker OPEN — rejecting request immediately "
                f"(rid={request_id})"
            )
            clear_request_id()
            return {
                "response": (
                    "I'm temporarily unable to process requests. "
                    "Please try again in a moment."
                ),
                "error": "circuit_open",
                "error_type": "external_api",
                "request_id": request_id,
                "processing_time_seconds": (datetime.now(timezone.utc) - start_time).total_seconds(),
            }

        MAX_RETRIES = 2
        BACKOFF_SCHEDULE = [1.0, 3.0]  # Exponential backoff: 1s, 3s

        for attempt in range(MAX_RETRIES + 1):
            try:
                final_state = await orchestrator.ainvoke(state, config={"recursion_limit": 15})
                circuit.record_success()
                break
            except Exception as workflow_err:
                is_retryable = _is_retryable(workflow_err)

                if attempt < MAX_RETRIES and is_retryable:
                    wait_time = BACKOFF_SCHEDULE[attempt]
                    logger.warning(
                        f"[ORCHESTRATOR] LLM retry {attempt + 1}/{MAX_RETRIES} "
                        f"after {wait_time}s: {workflow_err}"
                    )
                    await asyncio.sleep(wait_time)
                    continue

                # Out of retries or non-retryable — record failure and raise
                if is_retryable:
                    circuit.record_failure()
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
            },
            # Verification & quality metadata from pipeline node
            "verification": final_state.get("verification_report"),
            "verification_passed": final_state.get("verification_passed", True),
            "quality_score": final_state.get("quality_score"),
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
        # AUDIT LOGGING — structured compliance trail with token tracking
        # ================================================================
        total_tokens_used = 0
        tokens_input = 0
        tokens_output = 0
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
        response["performance"]["tokens_input"] = tokens_input
        response["performance"]["tokens_output"] = tokens_output
        response["performance"]["tokens_total"] = total_tokens_used

        # Post-call circuit breaker re-check: update state after recording usage
        if resolved_org_id is not None and db_session is not None:
            try:
                from services.ai_cost_tracker import check_circuit_breaker as _post_cb_check
                _, cb_post_reason = _post_cb_check(
                    org_id=resolved_org_id, db=db_session,
                )
                if cb_post_reason in ("warning", "critical"):
                    response["cost_warning"] = cb_post_reason
                    response.setdefault("headers", {})["X-AI-Cost-Warning"] = cb_post_reason
            except Exception:
                pass

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
                        if verification and hasattr(verification, 'faithfulness_score'):
                            if verification.faithfulness_score < 0.5:
                                # Very low faithfulness — block the response entirely
                                response["response"] = (
                                    "I'm not confident enough in this answer to share it "
                                    "— it involves compliance-sensitive information. "
                                    "Please consult your compliance team or check the "
                                    "guidelines directly."
                                )
                                response["blocked_by_verification"] = True
                                logger.warning(
                                    f"[HALLUCINATION] Response BLOCKED — faithfulness "
                                    f"({verification.faithfulness_score:.2%}) for compliance intent '{intent}'"
                                )
                            elif verification.faithfulness_score < 0.7:
                                response["response"] += "\n\n⚠️ This response may need human verification for accuracy."
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
        # TIMING SUMMARY + RESPONSE TIME TRACKING
        # ================================================================
        total_perf = (time.perf_counter() - start_perf) * 1000
        node_trace = final_state.get("node_trace", [])

        # Record response time for percentile tracking
        try:
            from .orchestration.performance_tracker import get_response_time_tracker
            model_used = final_state.get("model_used", "unknown")
            get_response_time_tracker().record(
                response_time_ms=total_perf,
                intent=intent,
                model=model_used
            )
        except Exception:
            pass  # Never fail the response for metrics

        # Add intent routing info to performance metrics
        response["performance"]["intent_method"] = intent_method
        response["performance"]["intent_classify_ms"] = timing["intent_classify"]
        response["performance"]["scoped_tool_names"] = scoped_tool_names
        response["performance"]["total_ms"] = round(total_perf, 1)

        logger.info(f"[ORCHESTRATOR] ========================================")
        logger.info(f"[ORCHESTRATOR] TIMING BREAKDOWN (v5 - Fast Path):")
        logger.info(f"  PHASE 1 - Intent Classification:")
        logger.info(f"    - intent_classify:  {timing['intent_classify']:>8.1f}ms ({intent_method})")
        logger.info(f"  PHASE 2 - Scoped Tool Loading:")
        logger.info(f"    - load_tools:       {timing['load_tools']:>8.1f}ms ({tool_count} tools)")
        logger.info(f"  Pipeline Execution:")
        logger.info(f"    - init_state:       {timing['init_state']:>8.1f}ms")
        logger.info(f"    - create_graph:     {timing['create_graph']:>8.1f}ms")
        logger.info(f"    - workflow_execute: {timing['workflow_execute']:>8.1f}ms")
        logger.info(f"    - build_response:   {timing['build_response']:>8.1f}ms")
        logger.info(f"  ----------------------------------------")
        logger.info(f"  TOTAL:                {total_perf:>8.1f}ms ({processing_time:.2f}s)")
        logger.info(f"[ORCHESTRATOR] Intent: {intent} -> Agents: {intent_agents}")
        logger.info(f"[ORCHESTRATOR] Scoped tools: {list(scoped_tools.keys())}")
        logger.info(f"[ORCHESTRATOR] Tools used: {len(final_state.get('tool_calls', []))} of {tool_count} available")
        logger.info(f"[ORCHESTRATOR] ========================================")
        logger.info(f"[ORCHESTRATOR] END | rid={request_id} | {processing_time:.2f}s total")
        logger.info(f"[ORCHESTRATOR] ========================================")

        response["request_id"] = request_id

        # ================================================================
        # POST-CONVERSATION MEMORY SAVE
        # Non-blocking: fires and forgets so memory failures never delay response
        # ================================================================
        if db_session and resolved_org_id is not None:
            try:
                async def _save_post_conversation_memory():
                    """Extract key facts and save conversation memory after response."""
                    # Issue 1 fix: Create a fresh DB session — the FastAPI Depends(get_db)
                    # session is closed after the response is sent, so background tasks
                    # must use their own session.
                    from db import SessionLocal
                    local_db = SessionLocal()
                    try:
                        from services.agent_memory_service import (
                            save_conversation_summary,
                            save_memory,
                            is_memory_enabled,
                        )

                        # Determine the primary agent role from intent routing
                        agent_role = (
                            intent_agents[0] if intent_agents else "pipeline_analyst"
                        )

                        # Skip if memory is not enabled for this role
                        if not is_memory_enabled(agent_role):
                            return

                        response_text = response.get("response", "")
                        if not response_text or len(response_text) < 10:
                            return

                        # Build a concise summary from message + response
                        summary = (
                            f"User asked: {message[:200]}"
                            f"{'...' if len(message) > 200 else ''}\n"
                            f"Agent responded about: {intent} "
                            f"(confidence={intent_confidence:.2f})"
                        )

                        # Save the conversation summary
                        conv_id = save_conversation_summary(
                            db=local_db,
                            user_id=int(user_id) if isinstance(user_id, str) and user_id.isdigit() else user_id,
                            org_id=resolved_org_id,
                            agent_role=agent_role,
                            messages=[
                                {"role": "user", "content": message},
                                {"role": "assistant", "content": response_text[:1000]},
                            ],
                            summary=summary,
                            key_points=[intent, f"tools_used:{tool_count}"],
                        )

                        # Detect user corrections/preferences/directives in the message
                        # Issue 3 fix: Require at least TWO signal phrases, or message
                        # must be short (under 200 chars) to avoid false positives on
                        # normal conversation like "I like the interest rates today".
                        _uid = int(user_id) if isinstance(user_id, str) and user_id.isdigit() else user_id
                        _preference_signals = [
                            "i prefer", "i like", "i want", "always ",
                            "never ", "don't ", "do not ", "stop ",
                            "from now on", "remember that", "keep in mind",
                        ]
                        _directive_signals = [
                            "always ", "never ", "from now on",
                            "make sure", "don't ever", "stop doing",
                            "remember to", "going forward",
                        ]

                        msg_lower = message.lower()

                        # Count how many signal phrases match
                        _pref_hits = sum(1 for sig in _preference_signals if sig in msg_lower)
                        _dir_hits = sum(1 for sig in _directive_signals if sig in msg_lower)

                        # Only trigger if 2+ signals match, OR message is short (a pure directive)
                        _is_short_message = len(message) < 200

                        # Issue 4 fix: Use microsecond granularity to avoid key collisions
                        _ts_key = int(datetime.now(timezone.utc).timestamp() * 1000000)

                        # Save as PREFERENCE if preference language detected
                        if _pref_hits >= 2 or (_pref_hits >= 1 and _is_short_message):
                            save_memory(
                                db=local_db,
                                user_id=_uid,
                                org_id=resolved_org_id,
                                key=f"user_preference_{intent}_{_ts_key}",
                                value=message[:500],
                                memory_type="preference",
                                agent_role=agent_role,
                                confidence=0.5,
                                conversation_id=conv_id,
                            )

                        # Save as DIRECTIVE if directive language detected
                        if _dir_hits >= 2 or (_dir_hits >= 1 and _is_short_message):
                            save_memory(
                                db=local_db,
                                user_id=_uid,
                                org_id=resolved_org_id,
                                key=f"user_directive_{intent}_{_ts_key}",
                                value=message[:500],
                                memory_type="directive",
                                agent_role=agent_role,
                                confidence=0.6,
                                conversation_id=conv_id,
                            )

                        # Commit memory writes (they use flush, need explicit commit)
                        local_db.commit()
                        logger.info(
                            "[MEMORY] Post-conversation save complete for user=%s role=%s conv_id=%s",
                            user_id, agent_role, conv_id,
                        )
                    except Exception as mem_err:
                        # Issue 5 fix: Use logger.error with exc_info for full stack trace
                        logger.error(
                            "[MEMORY] Post-conversation save failed: %s",
                            mem_err,
                            exc_info=True,
                        )
                        try:
                            local_db.rollback()
                        except Exception as rollback_err:
                            logger.error("[MEMORY] Rollback also failed: %s", rollback_err)
                    finally:
                        local_db.close()

                # Issue 2 fix: Store task reference to prevent garbage collection,
                # and add a done callback to surface any unhandled exceptions.
                _task = asyncio.create_task(_save_post_conversation_memory())
                _task.add_done_callback(
                    lambda t: logger.error("[MEMORY] Task failed: %s", t.exception())
                    if t.exception() else None
                )
                logger.debug("[ORCHESTRATOR] Post-conversation memory save task dispatched")
            except Exception as mem_setup_err:
                # Issue 5 fix: Use logger.error with exc_info instead of logger.warning
                logger.error(
                    "[MEMORY] Failed to dispatch memory save task: %s", mem_setup_err,
                    exc_info=True,
                )

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
