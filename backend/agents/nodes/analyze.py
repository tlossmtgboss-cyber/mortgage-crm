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

    # Task Management
    "get_tasks",             # Get tasks by timeframe
    "create_task",           # Create a new task
    "get_daily_priorities",  # Get prioritized daily actions

    # Market Intelligence
    "get_rate_lock_advisory", # Rate lock recommendations
]

ANALYZE_SYSTEM_PROMPT = """You are a query analyzer for a mortgage CRM AI assistant. Your job is to analyze user queries and select appropriate tools to gather data.

IMPORTANT: For most queries, you SHOULD select at least one tool to gather relevant data. Only use "general_query" intent if the question is truly abstract or philosophical with no data retrieval needed.

Given a user query, return a JSON object with these fields:

{
  "intent": "one of: pipeline_status, lead_management, team_performance, task_management, communication, document_analysis, market_intelligence, financial_analysis, predictive_analytics, action_request, general_query",
  "entities": {
    "loan_ids": [],
    "borrower_names": [],
    "amounts": [],
    "dates": [],
    "stages": [],
    "team_members": []
  },
  "urgency": "low, medium, high, or critical",
  "complexity": "simple, moderate, or complex",
  "required_tools": ["ALWAYS select at least one tool for data gathering"],
  "requires_action": true/false
}

Available tools:
{tools}

TOOL SELECTION GUIDE (be aggressive about selecting tools):
- "What should I focus on today?" -> intent: task_management, tools: ["get_daily_priorities", "get_tasks", "get_pipeline"]
- "Show me my pipeline" -> intent: pipeline_status, tools: ["get_pipeline", "get_pipeline_metrics"]
- "Should I lock rates?" -> intent: market_intelligence, tools: ["get_rate_lock_advisory", "get_pipeline"]
- "What are my priorities?" -> intent: task_management, tools: ["get_daily_priorities", "get_tasks"]
- "Any deals at risk?" -> intent: pipeline_status, tools: ["get_pipeline", "get_pipeline_metrics"]
- "Find loan for Smith" -> intent: pipeline_status, tools: ["search_loans"]
- "Search for lead John" -> intent: lead_management, tools: ["search_leads"]

Intent mapping:
- pipeline_status: Pipeline, loans, deals, stages, closing dates
- task_management: Tasks, focus, priorities, what to do, schedule
- market_intelligence: Rates, lock/float decisions, market conditions
- lead_management: Leads, prospects, nurturing
- action_request: Explicit requests to create, send, or update something

DEFAULT: If unsure, use task_management intent with ["get_daily_priorities", "get_pipeline"] tools.

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

        # Handle potential JSON wrapped in markdown code blocks
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
            response_text = response_text.strip()

        analysis = json.loads(response_text)

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
        # Fall back to general query
        return update_state(state, {
            "query_intent": QueryIntent.GENERAL_QUERY,
            "query_entities": {},
            "query_urgency": "medium",
            "query_complexity": "moderate",
            "required_tools": ["get_pipeline_summary"],  # Safe default
            "requires_action": False
        })

    except Exception as e:
        logger.error(f"Query analysis failed: {e}")
        state = add_error(state, f"Query analysis error: {str(e)}")
        return update_state(state, {
            "query_intent": QueryIntent.GENERAL_QUERY,
            "required_tools": ["get_pipeline_summary"],
            "requires_action": False
        })
