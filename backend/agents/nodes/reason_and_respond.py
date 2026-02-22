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
MODEL_SONNET = "claude-sonnet-4-20250514"   # Full power for complex analysis (~7-8s)


UNIFIED_SYSTEM_PROMPT = """You are Perennia AI, a mortgage assistant. Be EXTREMELY concise.

ACCURACY RULES (non-negotiable):
- ONLY state facts from the provided data — never fabricate rates, amounts, dates, or status
- If data is missing or incomplete, say so — do not guess or approximate
- For compliance/regulatory topics, note that verification with compliance staff is recommended

RESPONSE RULES:
- Keep responses under 3-4 sentences MAX
- Lead with the single most important fact
- Use bullet points only if listing 2-3 items
- NO lengthy explanations or context
- NO "recommended next steps" sections
- NO markdown headers

EXAMPLE GOOD RESPONSE:
"You have 1 overdue task: Call Trevor Hammond (was due Dec 3rd). Your schedule is clear otherwise."

EXAMPLE BAD RESPONSE (too long):
"Looking at your tasks, I can see that you have one overdue item that needs attention. The task is to call Trevor Hammond, which was originally scheduled for December 3rd at 2:00 PM. Since this is now overdue, you should prioritize this call... [continues for paragraphs]"

Be brief. Get to the point. Users are on mobile.

{intent_guidance}"""


# Lean prompt for simple/tool-formatting intents (~200 tokens vs ~800 for full prompt)
# Used with Haiku for schedule, billing, coaching, integrations, video intents
LEAN_SYSTEM_PROMPT = """You are Perennia AI, a mortgage assistant. Format the provided data into a brief, helpful response.

RULES:
- ONLY state facts from the data — never fabricate
- 2-3 sentences max
- Lead with the answer
- No markdown headers
- If data is missing, say so"""


INTENT_GUIDANCE = {
    QueryIntent.PIPELINE_STATUS: """OVERRIDE: Ignore the sentence limit when listing loans/borrowers — show all relevant names.

FOCUS ON:
- Overall pipeline health (count, volume, velocity)
- Stage distribution and bottlenecks
- Deals at risk or stalled — list each borrower by name with loan amount, stage, and days in stage
- Upcoming closings — list each borrower by name with closing date and readiness status

Never give generic summaries. Always name the specific borrowers.""",

    QueryIntent.LEAD_MANAGEMENT: """OVERRIDE: Ignore the sentence limit when listing leads — show all relevant names.

FOCUS ON:
- Lead pipeline health and conversion rates
- Where leads are getting stuck (bottlenecks)
- Specific leads needing immediate attention — list each lead by name with score, stage, and days since last contact
- Actionable next steps per lead (not generic advice)

Never say "follow up with your leads." Name the specific people.""",

    QueryIntent.TEAM_PERFORMANCE: """FOCUS ON:
- Individual and team productivity metrics
- Workload distribution
- SLA compliance
- Specific team members who need support""",

    QueryIntent.TASK_MANAGEMENT: """OVERRIDE: For priorities/daily briefing, ignore the sentence limit — list all relevant data.

FOCUS ON:
- Prioritized task list (urgent first)
- Overdue items needing immediate attention
- ALWAYS list specific borrower/client names from the data under each priority
- For each person listed, include relevant details (loan amount, stage, days overdue, expiration date)
- Group by priority area (e.g., follow-ups, missing docs, rate lock expirations)

FORMAT:
1. **Priority Area**: brief description
   - Borrower Name — key detail (e.g., $425K conventional, 3 days overdue)
   - Borrower Name — key detail
2. **Next Priority Area**: ...

Never give generic advice like "follow up with your leads." Always name the specific people.""",

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


# =============================================================================
# TIER 2: ROLE CONTEXT (~100 tokens, injected when user role is known)
# =============================================================================

_ROLE_CONTEXT = {
    "loan_officer": "USER ROLE: Loan Officer — prioritize personal pipeline, closings, commissions, borrower relationships, and task prioritization.",
    "processor": "USER ROLE: Processor — prioritize document completeness, condition clearing, workflow efficiency, and underwriting coordination.",
    "manager": "USER ROLE: Manager — prioritize team performance, pipeline health across team, resource allocation, SLA compliance, and capacity planning.",
    "admin": "USER ROLE: Admin — prioritize system configuration, user management, compliance oversight, and operational reporting.",
}


def _get_role_context(role: str) -> str:
    """Get concise role context for Tier 2 prompt injection."""
    return _ROLE_CONTEXT.get(role, "")


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

        # Handle greeting case - use LLM for natural, human-like response
        intent_str_check = state.get("intent_str", "")
        if data_quality == "not_needed" and intent_str_check == "greeting":
            logger.info("[REASON_AND_RESPOND] Greeting detected - generating natural response via LLM")

            # Initialize client for greeting response
            if anthropic_client is None:
                anthropic_client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

            # Use Haiku for fast, natural greeting response
            greeting_prompt = f"""The user just said: "{user_message}"

Respond naturally and warmly to their greeting. Match their energy - if they say "good morning", say good morning back. If they say "hey", be casual. If they say "hello", be friendly.

Keep it brief (1-2 sentences max). You're Perennia AI, a helpful mortgage assistant. After greeting them back, gently invite them to ask about their pipeline, leads, or anything else.

DO NOT use a canned/scripted response. Be natural and human."""

            greeting_response_obj = anthropic_client.messages.create(
                model=MODEL_HAIKU,
                max_tokens=150,
                system=[
                    {
                        "type": "text",
                        "text": "You are Perennia AI, a friendly mortgage assistant. Respond naturally to greetings in 1-2 sentences, then invite the user to ask about their pipeline, leads, or tasks.",
                        "cache_control": {"type": "ephemeral"}
                    }
                ],
                messages=[{"role": "user", "content": greeting_prompt}]
            )
            greeting_response = greeting_response_obj.content[0].text.strip()

            return update_state(state, {
                "analysis": "Greeting - natural response generated",
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

        # Inject Tier 2 role context if user role is available (~100 tokens)
        user_role = state.get("user_role", "")
        if user_role:
            role_context = _get_role_context(user_role)
            if role_context:
                intent_guidance = f"{role_context}\n\n{intent_guidance}" if intent_guidance else role_context

        # Build the system prompt
        system_prompt = UNIFIED_SYSTEM_PROMPT.format(intent_guidance=intent_guidance)

        # Build user context
        context_parts = [
            f"USER QUESTION: {user_message}",
            f"QUERY INTENT: {query_intent.value}",
            f"DATA QUALITY: {data_quality}",
        ]

        # Inject uploaded document text if present (one-shot, not in memory)
        doc_context = state.get("document_context")
        if doc_context:
            context_parts.append("")
            context_parts.append("=== UPLOADED DOCUMENT ===")
            context_parts.append(doc_context[:50_000])
            context_parts.append("=== END DOCUMENT ===")

        context_parts.extend([
            "",
            "=== GATHERED DATA ===",
            formatted_data
        ])

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

        # Token budget: data-heavy intents (priorities, pipeline, leads) need room to list names
        DATA_HEAVY_INTENTS = {"task_management", "pipeline_status", "lead_management", "predictive_analytics"}
        if use_haiku:
            max_tokens = 200
        elif intent_str in DATA_HEAVY_INTENTS or intent_str_override in ("priorities", "pipeline", "leads"):
            max_tokens = 1200
        else:
            max_tokens = 400

        # When document context is attached, ensure enough tokens for thorough analysis
        if doc_context:
            max_tokens = max(max_tokens, 2000)

        # Use lean prompt for simple tool-formatting intents (saves ~600 tokens per call)
        if use_haiku and intent_str not in ("greeting", "simple") and intent_str_override not in ("greeting", "simple"):
            system_prompt = LEAN_SYSTEM_PROMPT

        logger.info(f"[REASON_AND_RESPOND] Model selection: {model} (intent={intent_str}, intent_str_override={intent_str_override}, use_haiku_flag={use_haiku_flag})")

        # Single LLM call for both reasoning AND response generation
        # Use prompt caching on the system prompt to reduce cost on repeated calls
        llm_start = time.time()
        response = anthropic_client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=[
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"}
                }
            ],
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
