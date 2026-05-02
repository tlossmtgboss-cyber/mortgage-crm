"""
Reasoning Engine Node

This node analyzes the gathered data to generate insights, recommendations,
and a coherent understanding of the user's situation.
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
from .gather import format_gathered_data_for_llm

logger = logging.getLogger(__name__)


REASONING_SYSTEM_PROMPT = """You are an expert mortgage industry analyst and advisor working for a mortgage CRM system. Your job is to analyze data and provide actionable insights.

Given the user's query and gathered data, you must:
1. Analyze the data thoroughly
2. Extract key insights
3. Provide specific, actionable recommendations
4. Reason through the implications

Your response must be a JSON object with this structure:
{
  "analysis": "A detailed analysis paragraph explaining what you found",
  "insights": ["List of 3-5 key insights extracted from the data"],
  "recommendations": ["List of 3-5 specific, actionable recommendations"],
  "confidence_score": 0.85,
  "reasoning_chain": ["Step 1: First I looked at...", "Step 2: This revealed...", "Step 3: Therefore..."]
}

Guidelines:
- Be specific with numbers, names, and dates when available
- For pipeline questions: highlight bottlenecks, at-risk deals, approaching deadlines
- For team performance: identify top performers and those needing support
- For tasks: prioritize by urgency and impact
- For market intelligence: provide clear lock/float recommendations with reasoning
- For predictive analytics: explain the factors driving predictions

IMPORTANT: Only return valid JSON, no other text or markdown."""


INTENT_SPECIFIC_PROMPTS = {
    QueryIntent.PIPELINE_STATUS: """Focus your analysis on:
- Overall pipeline health and value
- Stage distribution and bottlenecks
- Deals at risk or stalled
- Upcoming closings and their readiness
- Compare to typical conversion rates""",

    QueryIntent.TEAM_PERFORMANCE: """Focus your analysis on:
- Individual and team productivity metrics
- Workload distribution
- SLA compliance
- Areas where team members excel or need support
- Capacity for new work""",

    QueryIntent.TASK_MANAGEMENT: """Focus your analysis on:
- Task prioritization by urgency and impact
- Overdue items needing immediate attention
- Dependencies between tasks
- Recommended task ordering
- Quick wins vs strategic priorities""",

    QueryIntent.MARKET_INTELLIGENCE: """Focus your analysis on:
- Current rate environment and trends
- MBS pricing and spread movements
- Economic indicators affecting rates
- Clear lock vs float recommendation with rationale
- Risk factors to watch""",

    QueryIntent.PREDICTIVE_ANALYTICS: """Focus your analysis on:
- Key risk indicators and warning signs
- Probability assessments with confidence levels
- Factors driving the predictions
- Recommended interventions
- Timeline for action""",

    QueryIntent.FINANCIAL_ANALYSIS: """Focus your analysis on:
- Revenue and profitability metrics
- Cost per loan and efficiency
- Trend analysis
- Cash flow implications
- Areas for cost optimization"""
}


async def reason_and_analyze(
    state: AgentState,
    anthropic_client: Anthropic = None
) -> AgentState:
    """
    Analyze gathered data to generate insights and recommendations.

    Args:
        state: Current agent state with gathered data
        anthropic_client: Optional pre-configured Anthropic client

    Returns:
        Updated state with analysis, insights, and recommendations
    """
    state = add_node_trace(state, "reason")
    node_start = time.time()

    try:
        # Check if we have enough data to analyze
        data_quality = state.get("data_quality", "insufficient")
        gathered_data = state.get("gathered_data", {})

        logger.info(f"[REASON] Data quality: {data_quality}, gathered_data keys: {list(gathered_data.keys())}")
        if data_quality == "insufficient" or not gathered_data:
            logger.warning("[REASON] Insufficient data for reasoning")
            return update_state(state, {
                "analysis": "Unable to complete analysis due to insufficient data.",
                "insights": ["Data gathering encountered issues"],
                "recommendations": ["Please try rephrasing your query or check system connectivity"],
                "confidence_score": 0.2,
                "reasoning_chain": ["Data was insufficient for analysis"]
            })

        # Format the gathered data for the LLM
        formatted_data = format_gathered_data_for_llm(state)

        # Build the analysis prompt
        user_message = state.get("user_message", "")
        query_intent = state.get("query_intent", QueryIntent.GENERAL_QUERY)
        user_role = state.get("user_role", "loan_officer")

        # Get intent-specific guidance
        intent_guidance = INTENT_SPECIFIC_PROMPTS.get(query_intent, "")

        context = f"""
User Query: {user_message}
User Role: {user_role}
Query Intent: {query_intent.value}
Data Quality: {data_quality}

{intent_guidance}

=== GATHERED DATA ===
{formatted_data}
"""

        # Call Claude for reasoning
        if anthropic_client is None:
            anthropic_client = get_anthropic_client()

        llm_start = time.time()
        response = anthropic_client.messages.create(
            model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
            max_tokens=2000,
            system=REASONING_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": context
                }
            ],
            timeout=30.0,
        )
        llm_time = (time.time() - llm_start) * 1000
        logger.info(f"[REASON] ⏱️ LLM call took {llm_time:.0f}ms (context: {len(context)} chars)")

        # Parse the response
        response_text = response.content[0].text.strip()

        # Handle potential JSON wrapped in markdown code blocks
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
            response_text = response_text.strip()

        reasoning = json.loads(response_text)

        # Update state with reasoning results
        state = update_state(state, {
            "analysis": reasoning.get("analysis", ""),
            "insights": reasoning.get("insights", []),
            "recommendations": reasoning.get("recommendations", []),
            "confidence_score": float(reasoning.get("confidence_score", 0.5)),
            "reasoning_chain": reasoning.get("reasoning_chain", [])
        })

        node_time = (time.time() - node_start) * 1000
        logger.info(f"[REASON] ⏱️ Total node time: {node_time:.0f}ms | {len(reasoning.get('insights', []))} insights, confidence={reasoning.get('confidence_score', 0)}")

        return state

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse reasoning response: {e}")
        state = add_error(state, f"Reasoning JSON parse error: {str(e)}")
        return update_state(state, {
            "analysis": "Analysis completed but formatting error occurred.",
            "insights": [],
            "recommendations": [],
            "confidence_score": 0.3,
            "reasoning_chain": [f"Parse error: {str(e)}"]
        })

    except Exception as e:
        logger.error(f"Reasoning failed: {e}")
        state = add_error(state, f"Reasoning error: {str(e)}")
        return update_state(state, {
            "analysis": "An error occurred during analysis.",
            "insights": [],
            "recommendations": [],
            "confidence_score": 0.0,
            "reasoning_chain": [f"Error: {str(e)}"]
        })


def synthesize_cross_tool_insights(state: AgentState) -> list:
    """
    Generate additional insights by combining data from multiple tools.

    Args:
        state: Agent state with gathered data from multiple tools

    Returns:
        List of cross-tool insights
    """
    gathered_data = state.get("gathered_data", {})
    insights = []

    # Example: Combine pipeline and task data
    pipeline = gathered_data.get("get_pipeline", {})
    tasks = gathered_data.get("get_tasks", {})

    if pipeline and tasks:
        # Check for misalignment between pipeline stage and tasks
        loan_stages = pipeline.get("loan_stages", {})
        task_count = tasks.get("count", 0)

        for stage, data in loan_stages.items():
            if "closing" in stage.lower() and data.get("count", 0) > 0:
                if task_count == 0:
                    insights.append(
                        f"Warning: {data['count']} loans in {stage} stage but no active tasks - may need attention"
                    )

    # Example: Combine market data and pipeline
    market = gathered_data.get("get_market_intelligence", {})
    if market and pipeline:
        if market.get("recommendation") == "LOCK" and pipeline.get("total_loans", 0) > 0:
            insights.append(
                "Market favors locking - consider reviewing all unlocked loans"
            )

    # Example: Combine performance and capacity
    capacity = gathered_data.get("get_employee_capacity", {})
    performance = gathered_data.get("get_team_performance", {})

    if capacity and performance:
        # Look for overloaded high performers
        pass  # Add specific logic based on data structure

    return insights
