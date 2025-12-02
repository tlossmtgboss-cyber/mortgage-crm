"""
Query Analyzer Node

This node analyzes the user's query to determine:
- Intent classification
- Entity extraction
- Required tools
- Urgency and complexity assessment
"""

import json
import logging
from typing import Any
from anthropic import Anthropic

from ..state import (
    AgentState,
    QueryIntent,
    add_node_trace,
    add_error,
    update_state
)

logger = logging.getLogger(__name__)

# Available tools that can be selected - MUST match names in service.py
AVAILABLE_TOOLS = [
    # Pipeline & Loan Tools (service.py names)
    "get_pipeline",          # Gets leads/loans by stage
    "search_loans",          # Search loans by name/number
    "search_leads",          # Search leads by name/email/phone
    "get_pipeline_metrics",  # Pipeline analytics

    # Lead Pipeline Intelligence Tools (NEW)
    "lead_status_insights",  # Lead pipeline coaching/analytics/bottlenecks
    "get_leads_by_status",   # Detailed lead lists for specific statuses

    # Task Management
    "get_tasks",             # Get tasks by timeframe
    "create_task",           # Create a new task
    "get_daily_priorities",  # Get prioritized daily actions

    # Market Intelligence
    "get_rate_lock_advisory", # Rate lock recommendations
]

ANALYZE_SYSTEM_PROMPT = """You are a query analyzer for a mortgage CRM AI assistant. Analyze user queries and select appropriate tools.

CRITICAL: Return ONLY a single-line JSON object. No line breaks inside the JSON. No text before or after.

Format: {"intent":"...","entities":{"loan_ids":[],"borrower_names":[],"amounts":[],"dates":[],"stages":[],"team_members":[]},"urgency":"...","complexity":"...","required_tools":[...],"requires_action":false}

Intent must be ONE of: pipeline_status, lead_management, team_performance, task_management, communication, document_analysis, market_intelligence, financial_analysis, predictive_analytics, action_request, general_query

ALWAYS select at least one tool in required_tools.

Available tools:
{tools}

### CRITICAL TOOL ROUTING RULES ###

**FOR LEAD QUESTIONS (highest priority):**
If the user mentions: "lead", "leads", "prospect", "prospects", "new lead", "lead pipeline", "lead conversion", "lead bottleneck", "nurture", "who to call", "speed to lead", or asks about converting/qualifying leads:
- ALWAYS use: lead_status_insights (for analytics, coaching, bottlenecks, conversion rates)
- ADD: get_leads_by_status (when user wants specific lead names/lists)
- Intent: lead_management

**FOR LOAN PIPELINE QUESTIONS:**
If user mentions: "loan", "loans", "deal", "deals", "closing", "processing", "underwriting", "funded":
- Use: get_pipeline, get_pipeline_metrics
- Intent: pipeline_status

Examples with EXACT required_tools:
- "How is my lead pipeline?" -> ["lead_status_insights"]
- "Where are leads getting stuck?" -> ["lead_status_insights"]
- "Give me lead coaching" -> ["lead_status_insights", "get_leads_by_status"]
- "Show my New leads" -> ["get_leads_by_status"]
- "Who should I call today?" -> ["lead_status_insights", "get_leads_by_status"]
- "What are my lead bottlenecks?" -> ["lead_status_insights"]
- "Daily briefing on leads" -> ["lead_status_insights", "get_leads_by_status"]
- "Show my pipeline" -> ["get_pipeline", "get_pipeline_metrics"]
- "What loans are closing soon?" -> ["get_pipeline"]
- "Top priorities today?" -> ["get_daily_priorities", "get_tasks"]
- "Should I lock rates?" -> ["get_rate_lock_advisory", "get_pipeline"]

Intent mapping:
- lead_management: Lead-related questions (ALWAYS use lead_status_insights)
- pipeline_status: Loan pipeline, deals, stages
- task_management: Tasks, priorities, schedule
- market_intelligence: Rates, lock/float decisions

DEFAULT: If unsure, use task_management with ["get_daily_priorities", "get_pipeline"].

Urgency:
- critical: Closing today, urgent issues
- high: Important items this week
- medium: Standard requests
- low: Informational queries

Return ONLY valid JSON."""


async def analyze_query(state: AgentState, anthropic_client: Anthropic = None) -> AgentState:
    """
    Analyze the user's query to extract intent, entities, and required tools.

    Args:
        state: Current agent state
        anthropic_client: Optional pre-configured Anthropic client

    Returns:
        Updated state with query analysis
    """
    state = add_node_trace(state, "analyze")

    try:
        user_message = state["user_message"]
        user_role = state.get("user_role", "loan_officer")

        # Build the analysis prompt
        tools_list = "\n".join(f"- {tool}" for tool in AVAILABLE_TOOLS)
        system_prompt = ANALYZE_SYSTEM_PROMPT.format(tools=tools_list)

        # Add context about the user
        context = f"User role: {user_role}\n"
        if state.get("conversation_history"):
            recent_history = state["conversation_history"][-3:]
            context += "Recent conversation:\n"
            for msg in recent_history:
                context += f"- {msg.get('role', 'user')}: {msg.get('content', '')[:100]}...\n"

        # Call Claude to analyze the query
        if anthropic_client is None:
            import os
            anthropic_client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

        response = anthropic_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            system=system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": f"{context}\n\nUser query: {user_message}"
                }
            ]
        )

        # Parse the response
        response_text = response.content[0].text.strip()
        logger.info(f"[ANALYZE] Raw response: {repr(response_text[:300])}")

        # Handle potential JSON wrapped in markdown code blocks
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
            response_text = response_text.strip()

        # Try to extract JSON from the response if it's mixed with text
        # Use a more robust approach: find first { and last }
        first_brace = response_text.find('{')
        last_brace = response_text.rfind('}')
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            response_text = response_text[first_brace:last_brace + 1]
            logger.info(f"[ANALYZE] Extracted JSON: {repr(response_text[:200])}")
        else:
            logger.warning(f"[ANALYZE] No JSON object found in response")

        analysis = json.loads(response_text)
        logger.info(f"[ANALYZE] Parsed successfully: intent={analysis.get('intent')}, tools={analysis.get('required_tools')}")

        # Map intent string to enum
        intent_map = {
            "pipeline_status": QueryIntent.PIPELINE_STATUS,
            "lead_management": QueryIntent.LEAD_MANAGEMENT,
            "team_performance": QueryIntent.TEAM_PERFORMANCE,
            "task_management": QueryIntent.TASK_MANAGEMENT,
            "communication": QueryIntent.COMMUNICATION,
            "document_analysis": QueryIntent.DOCUMENT_ANALYSIS,
            "market_intelligence": QueryIntent.MARKET_INTELLIGENCE,
            "financial_analysis": QueryIntent.FINANCIAL_ANALYSIS,
            "predictive_analytics": QueryIntent.PREDICTIVE_ANALYTICS,
            "action_request": QueryIntent.ACTION_REQUEST,
            "general_query": QueryIntent.GENERAL_QUERY,
        }

        intent = intent_map.get(analysis.get("intent", ""), QueryIntent.GENERAL_QUERY)

        # Filter required tools to only include valid ones
        required_tools = [
            tool for tool in analysis.get("required_tools", [])
            if tool in AVAILABLE_TOOLS
        ]

        # Update state with analysis results
        state = update_state(state, {
            "query_intent": intent,
            "query_entities": analysis.get("entities", {}),
            "query_urgency": analysis.get("urgency", "medium"),
            "query_complexity": analysis.get("complexity", "moderate"),
            "required_tools": required_tools,
            "requires_action": analysis.get("requires_action", False)
        })

        logger.info(f"Query analyzed: intent={intent.value}, tools={required_tools}")

        return state

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse analysis response: {e}")
        state = add_error(state, f"Query analysis JSON parse error: {str(e)}")
        # Fall back to task management with actual tool names
        return update_state(state, {
            "query_intent": QueryIntent.TASK_MANAGEMENT,
            "query_entities": {},
            "query_urgency": "medium",
            "query_complexity": "moderate",
            "required_tools": ["get_daily_priorities", "get_tasks", "get_pipeline"],  # Actual tool names
            "requires_action": False
        })

    except Exception as e:
        logger.error(f"Query analysis failed: {e}")
        state = add_error(state, f"Query analysis error: {str(e)}")
        return update_state(state, {
            "query_intent": QueryIntent.TASK_MANAGEMENT,
            "required_tools": ["get_daily_priorities", "get_tasks", "get_pipeline"],
            "requires_action": False
        })
