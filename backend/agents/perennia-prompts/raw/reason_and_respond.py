"""
Unified Reasoning + Response Node

This node combines the reasoning and response generation into a single LLM call,
reducing response time by ~5-7 seconds (eliminating one full LLM round-trip).

Replaces the sequential: reason.py -> respond.py
With a single: reason_and_respond.py
"""

import json
import logging
import os
import time
from typing import Any, List
from anthropic import Anthropic

from ..state import (
    AgentState,
    QueryIntent,
    add_node_trace,
    add_error,
    update_state
)
from ..intent_router import HAIKU_INTENTS

logger = logging.getLogger(__name__)


# =============================================================================
# MODEL SELECTION
# =============================================================================

# Models for different complexity levels
MODEL_HAIKU = "claude-haiku-4-5-20251001"   # Fast for simple queries (~1-2s)
MODEL_SONNET = "claude-sonnet-4-6"   # Full power for complex analysis (~5-7s)


UNIFIED_SYSTEM_PROMPT = """You are Perennia AI, an expert mortgage industry assistant. Your job is to analyze data AND generate a helpful response in one step.

PROCESS:
1. Analyze the gathered data thoroughly
2. Extract key insights (3-5 bullet points internally)
3. Formulate specific, actionable recommendations
4. Generate a clear, confident response for the user

RESPONSE STYLE:
- Lead with the most important information
- Be direct and actionable - no disclaimers or hedging
- Use specific numbers, names, and dates when available
- Structure with clear sections when appropriate
- Include 2-3 concrete next steps
- Professional but friendly tone

RESPONSE STRUCTURE:
1. Direct answer to the user's question
2. Key supporting details with specific data
3. Actionable recommendations (prioritized)
4. Brief follow-up suggestions (optional)

DO NOT use markdown headers (no # symbols). Write in natural, conversational paragraphs with bullet points where helpful.

{intent_guidance}"""


INTENT_GUIDANCE = {
    QueryIntent.PIPELINE_STATUS: """FOCUS ON:
- Overall pipeline health (count, volume, velocity)
- Stage distribution and bottlenecks
- Deals at risk or stalled (with specific names)
- Upcoming closings and their readiness""",

    QueryIntent.LEAD_MANAGEMENT: """FOCUS ON:
- Lead pipeline health and conversion rates
- Where leads are getting stuck (bottlenecks)
- Speed-to-lead metrics
- Specific leads needing immediate attention
- Actionable next steps for lead nurturing""",

    QueryIntent.TEAM_PERFORMANCE: """FOCUS ON:
- Individual and team productivity metrics
- Workload distribution
- SLA compliance
- Specific team members who need support""",

    QueryIntent.TASK_MANAGEMENT: """FOCUS ON:
- Prioritized task list (urgent first)
- Overdue items needing immediate attention
- Context for each task (borrower, loan details)
- Suggested task groupings for efficiency""",

    QueryIntent.MARKET_INTELLIGENCE: """FOCUS ON:
- Clear lock/float recommendation with rationale
- Current rate environment and trends
- Key factors driving the recommendation
- Timeline considerations for action""",

    QueryIntent.PREDICTIVE_ANALYTICS: """FOCUS ON:
- Risk assessments with probability levels
- Key warning signs identified
- Recommended interventions prioritized
- Timeline for action""",

    QueryIntent.COMMUNICATION: """FOCUS ON:
- Confirmation of what was sent/done
- Summary of content
- Next steps if any""",

    QueryIntent.ACTION_REQUEST: """FOCUS ON:
- What was done or will be done
- Confirmation of details
- Any items needing confirmation
- Result of the action"""
}


def format_gathered_data_for_llm(gathered_data: dict) -> str:
    """Format gathered data into a concise string for LLM consumption."""
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


def generate_follow_up_suggestions(intent: QueryIntent) -> List[str]:
    """Generate contextual follow-up suggestions based on intent."""
    suggestions_map = {
        QueryIntent.PIPELINE_STATUS: [
            "What are my upcoming closings this week?",
            "Which deals are at risk?",
            "Show me bottlenecks in the pipeline"
        ],
        QueryIntent.LEAD_MANAGEMENT: [
            "Who should I call first?",
            "Show me my hottest leads",
            "What's my conversion rate?"
        ],
        QueryIntent.TEAM_PERFORMANCE: [
            "Who has capacity for new loans?",
            "What are the SLA violations?",
            "Compare this month to last month"
        ],
        QueryIntent.TASK_MANAGEMENT: [
            "What's overdue?",
            "Email me my task summary",
            "What should I prioritize?"
        ],
        QueryIntent.MARKET_INTELLIGENCE: [
            "Should I lock or float on my 30-day closes?",
            "What's the rate trend this week?",
            "How do rates compare to last month?"
        ],
        QueryIntent.PREDICTIVE_ANALYTICS: [
            "Which deals are most likely to close?",
            "Who should I follow up with today?",
            "Forecast my revenue for next month"
        ],
    }

    return suggestions_map.get(intent, [
        "Show me my pipeline",
        "What are my priorities today?",
        "Any deals at risk?"
    ])[:3]


async def reason_and_respond(
    state: AgentState,
    anthropic_client: Anthropic = None
) -> AgentState:
    """
    Unified reasoning + response generation in a single LLM call.

    This combines the previous reason.py and respond.py nodes into one,
    eliminating one full LLM round-trip (~5-7 seconds savings).

    Args:
        state: Current agent state with gathered data
        anthropic_client: Optional pre-configured Anthropic client

    Returns:
        Updated state with analysis, insights, recommendations, and response
    """
    state = add_node_trace(state, "reason_and_respond")
    node_start = time.time()

    try:
        # Get context from state
        user_message = state.get("user_message", "")
        query_intent = state.get("query_intent", QueryIntent.GENERAL_QUERY)
        gathered_data = state.get("gathered_data", {})
        data_quality = state.get("data_quality", "unknown")
        actions_executed = state.get("actions_executed", [])
        actions_pending = state.get("actions_pending", [])
        errors = state.get("errors", [])

        # Handle insufficient data case (but NOT "not_needed" which is intentional for greetings)
        if data_quality == "insufficient":
            logger.warning("[REASON_AND_RESPOND] Insufficient data for analysis")
            return update_state(state, {
                "analysis": "Unable to complete analysis due to insufficient data.",
                "insights": ["Data gathering encountered issues"],
                "recommendations": ["Please try rephrasing your query or check system connectivity"],
                "confidence_score": 0.2,
                "response": "I apologize, but I couldn't retrieve the data needed to answer your question. Could you try rephrasing or asking something more specific?",
                "response_type": "text",
                "follow_up_suggestions": ["Show me my pipeline", "What are my priorities today?"]
            })

        # Handle greeting case - fast path with friendly response
        intent_str_check = state.get("intent_str", "")
        if data_quality == "not_needed" and intent_str_check == "greeting":
            logger.info("[REASON_AND_RESPOND] Greeting detected - using fast greeting response")
            greeting_response = f"Hello! I'm Perennia AI, your mortgage industry assistant. I'm here to help you with your pipeline, leads, tasks, rates, and more. What would you like to work on today?"
            return update_state(state, {
                "analysis": "Greeting detected",
                "insights": [],
                "recommendations": [],
                "confidence_score": 0.99,
                "response": greeting_response,
                "response_type": "text",
                "follow_up_suggestions": ["Show me my pipeline", "What are my priorities?", "How are my leads doing?"]
            })

        # Format gathered data
        formatted_data = format_gathered_data_for_llm(gathered_data)

        # Get intent-specific guidance
        intent_guidance = INTENT_GUIDANCE.get(query_intent, "")

        # Build the system prompt
        system_prompt = UNIFIED_SYSTEM_PROMPT.format(intent_guidance=intent_guidance)

        # Build user context
        context_parts = [
            f"USER QUESTION: {user_message}",
            f"QUERY INTENT: {query_intent.value}",
            f"DATA QUALITY: {data_quality}",
            "",
            "=== GATHERED DATA ===",
            formatted_data
        ]

        # Add action context if any
        if actions_executed:
            context_parts.append("\n=== ACTIONS COMPLETED ===")
            for action in actions_executed:
                status = "SUCCESS" if action.success else "FAILED"
                context_parts.append(f"- [{status}] {action.action_type}: {action.message}")

        if actions_pending:
            context_parts.append("\n=== ACTIONS AWAITING CONFIRMATION ===")
            for action in actions_pending:
                context_parts.append(f"- {action.get('type', 'Unknown action')}")

        if errors:
            context_parts.append("\n=== NOTES ===")
            context_parts.append("Some data retrieval encountered issues but partial data is available.")

        context = "\n".join(context_parts)

        # Initialize client if needed
        if anthropic_client is None:
            anthropic_client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

        # Select model based on intent complexity
        # Get intent string from state (could be QueryIntent enum or string)
        intent_str = query_intent.value if hasattr(query_intent, 'value') else str(query_intent)

        # Check for explicit use_haiku flag from analyze node (fastest path)
        use_haiku_flag = state.get("use_haiku", False)
        intent_str_override = state.get("intent_str", "")

        # Use Haiku if: explicit flag set, intent in HAIKU_INTENTS, data not needed (greeting), or data insufficient
        use_haiku = use_haiku_flag or intent_str in HAIKU_INTENTS or intent_str_override in HAIKU_INTENTS or data_quality in ("insufficient", "not_needed")
        model = MODEL_HAIKU if use_haiku else MODEL_SONNET
        max_tokens = 500 if use_haiku else 2500  # Smaller output for simple queries

        logger.info(f"[REASON_AND_RESPOND] Model selection: {model} (intent={intent_str}, intent_str_override={intent_str_override}, use_haiku_flag={use_haiku_flag})")

        # Single LLM call for both reasoning AND response generation
        llm_start = time.time()
        response = anthropic_client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": f"Analyze this data and provide a helpful response:\n\n{context}"
                }
            ]
        )
        llm_time = (time.time() - llm_start) * 1000
        logger.info(f"[REASON_AND_RESPOND] ⏱️ Unified LLM call took {llm_time:.0f}ms (model={model}, context: {len(context)} chars)")

        response_text = response.content[0].text.strip()

        # Extract insights from the response (first few sentences for logging)
        first_paragraph = response_text.split("\n\n")[0] if "\n\n" in response_text else response_text[:300]

        # Generate follow-up suggestions
        follow_ups = generate_follow_up_suggestions(query_intent)

        # Determine response type
        response_type = "text"
        if actions_pending:
            response_type = "action_confirmation"
        elif len(gathered_data) > 2:
            response_type = "structured"

        # Calculate confidence based on data quality and response length
        confidence = 0.85 if data_quality == "complete" else 0.6
        if len(response_text) > 500:
            confidence = min(confidence + 0.1, 0.95)

        # Update state with all results
        state = update_state(state, {
            "analysis": first_paragraph,
            "insights": [],  # Not separately extracted in unified mode
            "recommendations": [],  # Embedded in response
            "confidence_score": confidence,
            "reasoning_chain": ["Unified analysis and response generation"],
            "response": response_text,
            "response_type": response_type,
            "follow_up_suggestions": follow_ups
        })

        node_time = (time.time() - node_start) * 1000
        logger.info(f"[REASON_AND_RESPOND] ⏱️ Total node time: {node_time:.0f}ms | {len(response_text)} chars, type={response_type}")

        return state

    except Exception as e:
        logger.error(f"Unified reasoning/response failed: {e}", exc_info=True)
        state = add_error(state, f"Reason and respond error: {str(e)}")

        # Fallback response
        fallback = f"I apologize, but I encountered an issue processing your request. Could you try rephrasing your question?"

        return update_state(state, {
            "analysis": f"Error: {str(e)}",
            "insights": [],
            "recommendations": [],
            "confidence_score": 0.0,
            "response": fallback,
            "response_type": "text",
            "follow_up_suggestions": ["Show me my pipeline", "What are my priorities today?"]
        })
