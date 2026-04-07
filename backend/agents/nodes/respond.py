"""
Response Generator Node

This node generates the final user-facing response by synthesizing
analysis, insights, recommendations, and action results.
"""

import json
import logging
import time
from typing import Any
from anthropic import Anthropic

from ..anthropic_client import get_anthropic_client
from ..state import (
    AgentState,
    QueryIntent,
    add_node_trace,
    add_error,
    update_state
)
from .execute import format_action_confirmation_request

logger = logging.getLogger(__name__)


RESPONSE_SYSTEM_PROMPT = """You are an expert mortgage industry AI assistant. Your job is to generate helpful, actionable responses for loan officers and mortgage professionals.

Given the analysis, insights, and recommendations, create a natural, conversational response.

Guidelines:
- Be concise but thorough
- Lead with the most important information
- Use specific numbers, names, and dates when available
- Format lists and key points clearly
- If actions were taken, confirm what was done
- If actions are pending, explain what needs confirmation
- Suggest relevant follow-up questions
- Use a professional but friendly tone

Response structure:
1. Direct answer to the user's question
2. Key supporting details/data
3. Actionable recommendations (if any)
4. Brief follow-up suggestions

DO NOT use markdown headers (no # symbols). Use plain text with clear organization.
DO NOT include JSON in your response - write natural language only."""


INTENT_RESPONSE_TEMPLATES = {
    QueryIntent.PIPELINE_STATUS: """Focus the response on:
- Overall pipeline health and value
- Key deals and their status
- Items needing attention
- Upcoming deadlines""",

    QueryIntent.TEAM_PERFORMANCE: """Focus the response on:
- Performance highlights and concerns
- Workload balance
- Specific team member insights
- Capacity recommendations""",

    QueryIntent.TASK_MANAGEMENT: """Focus the response on:
- Prioritized task list
- Urgent items first
- Context for each task (borrower, loan)
- Suggested task groupings""",

    QueryIntent.MARKET_INTELLIGENCE: """Focus the response on:
- Clear lock/float recommendation
- Supporting market data
- Key factors driving the recommendation
- Timeline considerations""",

    QueryIntent.PREDICTIVE_ANALYTICS: """Focus the response on:
- Risk assessments with probabilities
- Key warning signs
- Recommended interventions
- Priority order for attention""",

    QueryIntent.COMMUNICATION: """Focus the response on:
- Confirmation of what was sent/done
- Summary of content
- Next steps if any
- Follow-up timing""",

    QueryIntent.ACTION_REQUEST: """Focus the response on:
- What was done or will be done
- Confirmation of details
- Any items needing confirmation
- Result of the action"""
}


async def generate_response(
    state: AgentState,
    anthropic_client: Anthropic = None
) -> AgentState:
    """
    Generate the final response to send to the user.

    Args:
        state: Current agent state with analysis and action results
        anthropic_client: Optional pre-configured Anthropic client

    Returns:
        Updated state with final response
    """
    state = add_node_trace(state, "respond")
    node_start = time.time()

    try:
        # Gather all the context for response generation
        user_message = state.get("user_message", "")
        query_intent = state.get("query_intent", QueryIntent.GENERAL_QUERY)
        analysis = state.get("analysis", "")
        insights = state.get("insights", [])
        recommendations = state.get("recommendations", [])
        actions_executed = state.get("actions_executed", [])
        actions_pending = state.get("actions_pending", [])
        confidence_score = state.get("confidence_score", 0.5)
        gathered_data = state.get("gathered_data", {})
        errors = state.get("errors", [])

        # Get intent-specific guidance
        intent_guidance = INTENT_RESPONSE_TEMPLATES.get(query_intent, "")

        # Build context for response generation
        context_parts = [f"User Question: {user_message}"]
        context_parts.append(f"\nQuery Intent: {query_intent.value}")
        context_parts.append(f"Confidence: {confidence_score:.0%}")

        if analysis:
            context_parts.append(f"\nAnalysis:\n{analysis}")

        if insights:
            context_parts.append(f"\nKey Insights:")
            for insight in insights:
                context_parts.append(f"- {insight}")

        if recommendations:
            context_parts.append(f"\nRecommendations:")
            for rec in recommendations:
                context_parts.append(f"- {rec}")

        # Include key data points from gathered data
        if gathered_data:
            context_parts.append("\nRelevant Data:")
            for tool_name, data in gathered_data.items():
                if isinstance(data, dict):
                    # Include summary-level data
                    summary_keys = ["count", "total", "summary", "recommendation"]
                    for key in summary_keys:
                        if key in data:
                            context_parts.append(f"- {tool_name} {key}: {data[key]}")

        # Include action results
        if actions_executed:
            context_parts.append("\nActions Completed:")
            for action in actions_executed:
                status = "✓" if action.success else "✗"
                context_parts.append(f"{status} {action.action_type}: {action.message}")

        if actions_pending:
            context_parts.append("\nActions Awaiting Confirmation:")
            for action in actions_pending:
                context_parts.append(f"- {action.get('type', 'Unknown action')}")

        if errors:
            context_parts.append("\nNotes: Some data could not be retrieved")

        context = "\n".join(context_parts)

        # Generate response with Claude
        if anthropic_client is None:
            anthropic_client = get_anthropic_client()

        llm_start = time.time()
        response = anthropic_client.messages.create(
            model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514"),
            max_tokens=1500,
            system=f"{RESPONSE_SYSTEM_PROMPT}\n\n{intent_guidance}",
            messages=[
                {
                    "role": "user",
                    "content": context
                }
            ],
            timeout=30.0,
        )
        llm_time = (time.time() - llm_start) * 1000
        logger.info(f"[RESPOND] ⏱️ LLM call took {llm_time:.0f}ms (context: {len(context)} chars)")

        response_text = response.content[0].text.strip()

        # Append action confirmation if there are pending actions
        if actions_pending:
            confirmation_text = format_action_confirmation_request(actions_pending)
            if confirmation_text:
                response_text += f"\n\n{confirmation_text}"

        # Generate follow-up suggestions
        follow_ups = generate_follow_up_suggestions(state, query_intent)

        # Determine response type
        response_type = "text"
        if actions_pending:
            response_type = "action_confirmation"
        elif gathered_data and len(gathered_data) > 2:
            response_type = "structured"

        # Update state with final response
        state = update_state(state, {
            "response": response_text,
            "response_type": response_type,
            "follow_up_suggestions": follow_ups
        })

        node_time = (time.time() - node_start) * 1000
        logger.info(f"[RESPOND] ⏱️ Total node time: {node_time:.0f}ms | {len(response_text)} chars, type={response_type}")

        return state

    except Exception as e:
        logger.error(f"Response generation failed: {e}")
        state = add_error(state, f"Response generation error: {str(e)}")

        # Fallback response
        fallback_response = generate_fallback_response(state)
        return update_state(state, {
            "response": fallback_response,
            "response_type": "text",
            "follow_up_suggestions": []
        })


def generate_follow_up_suggestions(state: AgentState, intent: QueryIntent) -> list:
    """
    Generate contextual follow-up question suggestions.

    Args:
        state: Current agent state
        intent: Query intent

    Returns:
        List of follow-up suggestion strings
    """
    suggestions = []

    if intent == QueryIntent.PIPELINE_STATUS:
        suggestions = [
            "What are my upcoming closings this week?",
            "Which deals are at risk?",
            "Show me bottlenecks in the pipeline"
        ]
    elif intent == QueryIntent.TEAM_PERFORMANCE:
        suggestions = [
            "Who has capacity for new loans?",
            "What are the SLA violations?",
            "Compare this month to last month"
        ]
    elif intent == QueryIntent.TASK_MANAGEMENT:
        suggestions = [
            "What's overdue?",
            "Email me my task summary",
            "What should I prioritize?"
        ]
    elif intent == QueryIntent.MARKET_INTELLIGENCE:
        suggestions = [
            "Should I lock or float on my 30-day closes?",
            "What's the rate trend this week?",
            "How do rates compare to last month?"
        ]
    elif intent == QueryIntent.PREDICTIVE_ANALYTICS:
        suggestions = [
            "Which deals are most likely to close?",
            "Who should I follow up with today?",
            "Forecast my revenue for next month"
        ]
    else:
        suggestions = [
            "Show me my pipeline",
            "What are my priorities today?",
            "Any deals at risk?"
        ]

    return suggestions[:3]  # Return top 3


def generate_fallback_response(state: AgentState) -> str:
    """
    Generate a fallback response when normal generation fails.

    Args:
        state: Current agent state

    Returns:
        Fallback response string
    """
    user_message = state.get("user_message", "your request")
    errors = state.get("errors", [])

    response = f"I apologize, but I encountered an issue while processing \"{user_message}\"."

    if errors:
        response += " There were some technical difficulties retrieving the data."

    response += " Could you try rephrasing your question or asking something more specific?"

    # Include any partial analysis that was completed
    analysis = state.get("analysis", "")
    if analysis and len(analysis) > 50:
        response += f"\n\nBased on partial analysis: {analysis[:300]}..."

    return response


def format_structured_response(state: AgentState) -> dict:
    """
    Format the response as a structured object for rich UI rendering.

    Args:
        state: Agent state with complete response data

    Returns:
        Structured response dictionary
    """
    return {
        "text": state.get("response", ""),
        "intent": state.get("query_intent", QueryIntent.GENERAL_QUERY).value,
        "confidence": state.get("confidence_score", 0.5),
        "insights": state.get("insights", []),
        "recommendations": state.get("recommendations", []),
        "actions_completed": [
            {
                "type": a.action_type,
                "success": a.success,
                "message": a.message
            }
            for a in state.get("actions_executed", [])
        ],
        "actions_pending": state.get("actions_pending", []),
        "follow_ups": state.get("follow_up_suggestions", []),
        "data_quality": state.get("data_quality", "unknown"),
        "processing_trace": state.get("node_trace", [])
    }
