"""
AgentState - Central state management for LangGraph AI Agent

This module defines the state schema that flows through all nodes in the
LangGraph orchestrator. Each node can read from and write to this shared state.
"""

from typing import TypedDict, Literal, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class QueryIntent(str, Enum):
    """Classified intent types for incoming queries"""
    PIPELINE_STATUS = "pipeline_status"
    LEAD_MANAGEMENT = "lead_management"
    TEAM_PERFORMANCE = "team_performance"
    TASK_MANAGEMENT = "task_management"
    COMMUNICATION = "communication"
    DOCUMENT_ANALYSIS = "document_analysis"
    MARKET_INTELLIGENCE = "market_intelligence"
    FINANCIAL_ANALYSIS = "financial_analysis"
    PREDICTIVE_ANALYTICS = "predictive_analytics"
    ACTION_REQUEST = "action_request"
    GENERAL_QUERY = "general_query"
    UNKNOWN = "unknown"


@dataclass
class ToolCall:
    """Represents a tool call made during data gathering"""
    tool_name: str
    arguments: dict
    result: Optional[Any] = None
    error: Optional[str] = None
    execution_time_ms: Optional[float] = None


@dataclass
class ActionResult:
    """Result of an action execution"""
    action_type: str
    success: bool
    message: str
    data: Optional[dict] = None
    error: Optional[str] = None


class AgentState(TypedDict, total=False):
    """
    Central state object that flows through the LangGraph agent.

    This state is passed between nodes and allows them to communicate
    and build upon each other's work.
    """

    # === Input Fields ===
    user_message: str                    # Original user query
    user_id: str                         # Authenticated user ID
    user_email: str                      # User's email address
    user_role: str                       # User's role (loan_officer, manager, etc.)
    organization_id: Optional[int]       # Tenant isolation: org the user belongs to
    conversation_id: Optional[str]       # For multi-turn conversations

    # === Query Analysis (from analyze node) ===
    query_intent: QueryIntent            # Classified intent
    query_entities: dict                 # Extracted entities (names, dates, amounts)
    extracted_entities: dict             # Special entities from pattern matching (phone numbers, etc.)
    query_urgency: Literal["low", "medium", "high", "critical"]
    query_complexity: Literal["simple", "moderate", "complex"]
    required_tools: list[str]            # Tools needed to answer query
    requires_action: bool                # Whether query needs action vs just info
    analysis_method: str                 # How query was analyzed (pattern_match, llm, fallback)

    # === Model Selection (for optimized responses) ===
    use_haiku: bool                      # Flag to use fast Haiku model for simple queries
    intent_str: str                      # String intent for model selection (greeting, simple, etc.)
    intent_agents: list[str]             # Agents assigned to handle this intent
    intent_confidence: float             # Confidence score from intent classification

    # === Data Gathering (from gather node) ===
    tool_calls: list[ToolCall]           # Tools called and their results
    gathered_data: dict                  # Consolidated data from all tools
    data_quality: Literal["complete", "partial", "insufficient", "not_needed"]  # not_needed for greetings
    missing_data: list[str]              # Data that couldn't be retrieved

    # === Reasoning (from reason node) ===
    analysis: str                        # Detailed analysis of the data
    insights: list[str]                  # Key insights extracted
    recommendations: list[str]           # Actionable recommendations
    confidence_score: float              # Confidence in the analysis (0-1)
    reasoning_chain: list[str]           # Step-by-step reasoning trace

    # === Action Execution (from execute node) ===
    deferred_actions: list[dict]         # Actions deferred from gather to execute (need LLM content)
    actions_requested: list[dict]        # Actions user requested
    actions_executed: list[ActionResult] # Results of executed actions
    actions_pending: list[dict]          # Actions requiring confirmation

    # === Response Generation (from respond node) ===
    response: str                        # Final formatted response
    response_type: Literal["text", "structured", "action_confirmation"]
    follow_up_suggestions: list[str]     # Suggested next queries

    # === Metadata ===
    node_trace: list[str]                # Which nodes have processed this state
    start_time: datetime                 # When processing started
    errors: list[str]                    # Any errors encountered

    # === Active Entity Context (from CRM UI) ===
    active_lead_id: Optional[int]        # Lead the user is currently viewing in the CRM
    active_loan_id: Optional[int]        # Loan the user is currently viewing in the CRM
    active_entity_data: Optional[dict]   # Auto-fetched details for the active lead/loan

    # === Context & Memory ===
    conversation_history: list[dict]     # Previous turns in conversation
    user_context: dict                   # User preferences and context
    cached_data: dict                    # Data cached for reuse
    document_context: Optional[str]      # Text from user-uploaded document
    user_memories: list                  # Retrieved AgentMemory rows for this user
    memory_context: str                  # Formatted memory string for prompt injection

    # === Token Tracking & Observability ===
    tokens_input: int                    # Input tokens from LLM API response
    tokens_output: int                   # Output tokens from LLM API response
    model_used: str                      # Which model was used (e.g. claude-sonnet-4-20250514)

    # === Verification & Quality ===
    verification_report: Optional[dict]  # Hallucination verification report summary
    quality_score: Optional[dict]        # Quality analysis score and breakdown
    verification_passed: bool            # Whether verification found no high-confidence hallucinations


def create_initial_state(
    user_message: str,
    user_id: str,
    user_email: str,
    user_role: str = "loan_officer",
    organization_id: Optional[int] = None,
    conversation_id: Optional[str] = None,
    conversation_history: Optional[list] = None,
    active_lead_id: Optional[int] = None,
    active_loan_id: Optional[int] = None,
) -> AgentState:
    """
    Create initial state for a new agent run.

    Args:
        user_message: The user's input query
        user_id: Authenticated user ID
        user_email: User's email address
        user_role: User's role in the system
        organization_id: Tenant org ID for data isolation
        conversation_id: Optional ID for multi-turn conversations
        conversation_history: Previous messages in the conversation
        active_lead_id: Lead ID the user is currently viewing in the CRM UI
        active_loan_id: Loan ID the user is currently viewing in the CRM UI

    Returns:
        AgentState: Initialized state ready for processing
    """
    return AgentState(
        # Input
        user_message=user_message,
        user_id=user_id,
        user_email=user_email,
        user_role=user_role,
        organization_id=organization_id,
        conversation_id=conversation_id,

        # Query Analysis (to be filled by analyze node)
        query_intent=QueryIntent.UNKNOWN,
        query_entities={},
        query_urgency="medium",
        query_complexity="moderate",
        required_tools=[],
        requires_action=False,

        # Data Gathering (to be filled by gather node)
        tool_calls=[],
        gathered_data={},
        data_quality="insufficient",
        missing_data=[],

        # Reasoning (to be filled by reason node)
        analysis="",
        insights=[],
        recommendations=[],
        confidence_score=0.0,
        reasoning_chain=[],

        # Action Execution (to be filled by execute node)
        deferred_actions=[],
        actions_requested=[],
        actions_executed=[],
        actions_pending=[],

        # Response (to be filled by respond node)
        response="",
        response_type="text",
        follow_up_suggestions=[],

        # Metadata
        node_trace=[],
        start_time=datetime.now(timezone.utc),
        errors=[],

        # Active Entity Context (from CRM UI)
        active_lead_id=active_lead_id,
        active_loan_id=active_loan_id,
        active_entity_data=None,

        # Context
        conversation_history=conversation_history or [],
        user_context={},
        cached_data={},

        # Memory
        user_memories=[],
        memory_context="",

        # Verification & Quality
        verification_report=None,
        quality_score=None,
        verification_passed=True,
    )


def update_state(state: AgentState, updates: dict) -> AgentState:
    """
    Update state with new values, creating a new state object.

    Args:
        state: Current state
        updates: Dictionary of updates to apply

    Returns:
        AgentState: New state with updates applied
    """
    new_state = dict(state)
    new_state.update(updates)
    return AgentState(**new_state)


def add_node_trace(state: AgentState, node_name: str) -> AgentState:
    """Record that a node has processed this state"""
    node_trace = list(state.get("node_trace", []))
    node_trace.append(f"{node_name}:{datetime.now(timezone.utc).isoformat()}")
    return update_state(state, {"node_trace": node_trace})


def add_error(state: AgentState, error: str) -> AgentState:
    """Add an error to the state"""
    errors = list(state.get("errors", []))
    errors.append(f"[{datetime.now(timezone.utc).isoformat()}] {error}")
    return update_state(state, {"errors": errors})
