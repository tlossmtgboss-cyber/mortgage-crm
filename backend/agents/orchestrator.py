"""
LangGraph Orchestrator

This module creates and manages the LangGraph workflow that coordinates
all the agent nodes for processing user queries.
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

logger = logging.getLogger(__name__)


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
    tool_functions: Dict[str, Callable] = None,
    anthropic_client: Anthropic = None,
    autonomous_mode: bool = True,
    conversation_id: Optional[str] = None,
    conversation_history: Optional[list] = None,
    return_structured: bool = False
) -> Dict[str, Any]:
    """
    Run the full orchestrator pipeline on a user message.

    Args:
        message: User's input message
        user_id: Authenticated user ID
        user_email: User's email address
        user_role: User's role in the system
        tool_functions: Available tool functions
        anthropic_client: Pre-configured Anthropic client
        autonomous_mode: Whether to auto-execute actions
        conversation_id: Optional conversation ID for multi-turn
        conversation_history: Previous conversation messages
        return_structured: Whether to return structured response

    Returns:
        Response dictionary with text, metadata, and optional structured data
    """
    start_time = datetime.utcnow()

    try:
        # Create initial state
        state = create_initial_state(
            user_message=message,
            user_id=user_id,
            user_email=user_email,
            user_role=user_role,
            conversation_id=conversation_id,
            conversation_history=conversation_history
        )

        # Create and run the orchestrator
        orchestrator = create_orchestrator(
            tool_functions=tool_functions,
            anthropic_client=anthropic_client,
            autonomous_mode=autonomous_mode
        )

        # Execute the workflow
        final_state = await orchestrator.ainvoke(state)

        # Calculate processing time
        processing_time = (datetime.utcnow() - start_time).total_seconds()

        # Build response
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
            "actions_pending": final_state.get("actions_pending", [])
        }

        if return_structured:
            response["structured"] = format_structured_response(final_state)

        # Log any errors that occurred
        errors = final_state.get("errors", [])
        if errors:
            logger.warning(f"Orchestrator completed with errors: {errors}")
            response["warnings"] = errors

        # Get timing breakdown from node_trace
        node_trace = final_state.get("node_trace", [])
        logger.info(
            f"[ORCHESTRATOR] ⏱️ Total: {processing_time:.2f}s | "
            f"intent={response['intent']}, confidence={response['confidence']:.2f}, "
            f"nodes={node_trace}"
        )

        return response

    except Exception as e:
        logger.error(f"Orchestrator failed: {e}", exc_info=True)
        return {
            "response": f"I apologize, but I encountered an error processing your request. Please try again.",
            "error": str(e),
            "processing_time_seconds": (datetime.utcnow() - start_time).total_seconds()
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
        tool_functions: Dict[str, Callable] = None,
        anthropic_client: Anthropic = None,
        autonomous_mode: bool = True
    ):
        self.user_id = user_id
        self.user_email = user_email
        self.user_role = user_role
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
