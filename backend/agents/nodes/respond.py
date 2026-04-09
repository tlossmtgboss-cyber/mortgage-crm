"""
Response Generator Node

This node generates the final user-facing response by synthesizing
analysis, insights, recommendations, and action results.
"""

import json
import logging
import os
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


RESPONSE_SYSTEM_PROMPT = """You are Aria, the AI assistant for Perennia AI. You help loan officers manage their pipeline, communicate with borrowers, and get things done fast.

You are ACTION-ORIENTED. When the user asks you to do something, DO IT using the available tools - do not just describe what they could do. You have full access to the CRM and can execute actions on their behalf.

CORE BEHAVIOR:
- When the user says "send an email to [person]", USE the send_email tool. Do not just draft it.
- When the user says "create a task", USE the create_task tool. Do not just suggest it.
- When the user says "call [person]", USE the click_to_dial tool. Do not just provide the number.
- When the user says "text [person]", USE the send_sms tool. Do not just suggest it.
- When the user asks for data (pipeline, leads, tasks), PULL it from the CRM and present REAL numbers.

AFTER TAKING ACTION, confirm clearly:
- "Done! I sent the email to john@example.com with subject 'Rate Lock Update'."
- "Done! I created 3 follow-up tasks for your processing loans."
- "Done! Initiating call to (843) 555-1234."
- Do NOT say "I would recommend sending..." or "You could create a task..." - just DO it.

WHEN YOU CANNOT ACT:
- If a borrower has no email address on file, say so: "I don't have an email address for Sarah Thompson. Want me to search by a different field?"
- If required details are missing, ask for them specifically: "What should the email subject be?" or "When should this task be due?"
- Never fabricate contact info, loan amounts, or borrower details. Only use data from the CRM context provided.

RESPONSE STYLE:
- Be concise. Lead with the result, not the process.
- Use specific names, numbers, dates, and dollar amounts from CRM data.
- Skip pleasantries and filler. Get to the point.
- When listing items, keep it tight - no walls of text.
- Professional but direct tone.

DO NOT use markdown headers (no # symbols). Use plain text with clear organization.
DO NOT include JSON in your response - write natural language only.
DO NOT fabricate data. If a tool returned no results, say so honestly."""


INTENT_RESPONSE_TEMPLATES = {
    QueryIntent.PIPELINE_STATUS: """Focus the response on:
- Overall pipeline health and value (use real dollar amounts)
- Key deals and their status (use borrower names and loan stages)
- Items needing attention with specific next steps
- Upcoming deadlines with dates""",

    QueryIntent.TEAM_PERFORMANCE: """Focus the response on:
- Performance highlights and concerns with specific numbers
- Workload balance across team members
- Specific team member insights
- Capacity recommendations""",

    QueryIntent.TASK_MANAGEMENT: """Focus the response on:
- Prioritized task list with borrower names and context
- Urgent/overdue items first
- If user asked to CREATE tasks, confirm each one created with details
- If listing tasks, include due dates and associated borrowers""",

    QueryIntent.MARKET_INTELLIGENCE: """Focus the response on:
- Clear lock/float recommendation with specific rates
- Supporting market data
- Key factors driving the recommendation
- Timeline considerations for specific loans in pipeline""",

    QueryIntent.PREDICTIVE_ANALYTICS: """Focus the response on:
- Risk assessments with probabilities
- Key warning signs with specific borrower names
- Recommended interventions (offer to take action: "Want me to create follow-up tasks for these?")
- Priority order for attention""",

    QueryIntent.COMMUNICATION: """Focus the response on:
- Confirm EXACTLY what was sent: recipient, subject, channel (email/SMS/call)
- If the action succeeded, say "Done!" with specifics
- If it failed, explain why and offer alternatives
- Suggest logical next steps ("Want me to also create a follow-up task?")
IMPORTANT: Do NOT describe what you would send. Confirm what you DID send.""",

    QueryIntent.ACTION_REQUEST: """Focus the response on:
- Confirm the action was completed: "Done! I [action] for [details]."
- Include specific details: names, emails, phone numbers, dates used
- If multiple actions taken, list each with its result
- If any action failed or needs more info, say so clearly
- Offer related follow-up actions ("Want me to also...?")
IMPORTANT: Be direct. "Done! Created task 'Follow up with Sarah Thompson' due Friday." NOT "I would suggest creating a task..." """
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
            max_tokens=1000,  # Concise responses = fewer output tokens = faster
            system=f"{RESPONSE_SYSTEM_PROMPT}\n\n{intent_guidance}",
            messages=[
                {
                    "role": "user",
                    "content": context
                }
            ],
            timeout=15.0,  # Reduced from 30s — response should complete in <10s
        )
        llm_time = (time.time() - llm_start) * 1000
        logger.info(f"[RESPOND] LLM call took {llm_time:.0f}ms (context: {len(context)} chars)")

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
            "Email me a pipeline summary",
            "Create follow-up tasks for my at-risk deals",
            "Which deals are closing this week?"
        ]
    elif intent == QueryIntent.TEAM_PERFORMANCE:
        suggestions = [
            "Who has capacity for new loans?",
            "Create tasks to coach underperformers",
            "Compare this month to last month"
        ]
    elif intent == QueryIntent.TASK_MANAGEMENT:
        suggestions = [
            "Create tasks for all my overdue follow-ups",
            "Email me my task summary",
            "What should I prioritize today?"
        ]
    elif intent == QueryIntent.MARKET_INTELLIGENCE:
        suggestions = [
            "Text my borrowers about the rate drop",
            "Should I lock or float on my 30-day closes?",
            "Email rate alerts to my processing loans"
        ]
    elif intent == QueryIntent.PREDICTIVE_ANALYTICS:
        suggestions = [
            "Create follow-up tasks for at-risk deals",
            "Call my hottest lead",
            "Email borrowers who need attention"
        ]
    elif intent in (QueryIntent.COMMUNICATION, QueryIntent.ACTION_REQUEST):
        suggestions = [
            "Send a follow-up email to the same borrower",
            "Create a task to check back in 3 days",
            "Text my top 5 leads"
        ]
    else:
        suggestions = [
            "Show me my pipeline",
            "What are my priorities today?",
            "Call my top lead"
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
