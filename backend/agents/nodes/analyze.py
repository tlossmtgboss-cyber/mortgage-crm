"""
Query Analyzer Node (OPTIMIZED v2)

This node analyzes the user's query to determine:
- Intent classification
- Entity extraction
- Required tools
- Urgency and complexity assessment

OPTIMIZATION: Uses fast pattern matching for common queries to skip LLM call
- Pattern match first: ~10ms for known patterns (vs ~5-7s for LLM)
- Falls back to LLM for complex/ambiguous queries
"""

import json
import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple
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

    # Lead Pipeline Intelligence Tools
    "lead_status_insights",  # Lead pipeline coaching/analytics/bottlenecks
    "get_leads_by_status",   # Detailed lead lists for specific statuses

    # Task Management
    "get_tasks",             # Get tasks by timeframe
    "create_task",           # Create a new task
    "get_daily_priorities",  # Get prioritized daily actions

    # Market Intelligence
    "get_rate_lock_advisory", # Rate lock recommendations

    # Communication Tools
    "click_to_dial",         # Initiate outbound call
    "make_call",             # Alias for click_to_dial
    "send_sms",              # Send SMS message
    "send_text",             # Alias for send_sms
]


# =============================================================================
# FAST PATTERN MATCHING (skip LLM for common queries)
# =============================================================================

INTENT_PATTERNS = {
    # Task/Priority queries - most common
    "task_management": {
        "patterns": [
            r"(my |what are |show me )?(top |daily |today'?s? )?priorit(y|ies)",
            r"what (should|do) i (do|focus on|work on)( first| today| next)?",
            r"(my |today'?s? )?tasks?( for today| list)?",
            r"what('?s| is) (on my|my) (plate|agenda|schedule|to-?do)",
            r"(top|next) (items?|things?|actions?)( to do)?",
            r"(daily |morning )?brief(ing)?",
            r"(start|begin) (my|the) day",
            r"what('?s| is) overdue",
            r"urgent (items?|tasks?|things?)",
        ],
        "intent": QueryIntent.TASK_MANAGEMENT,
        "tools": ["get_daily_priorities", "get_tasks"],
        "urgency": "high",
        "complexity": "simple",
        "confidence": 0.95
    },

    # Lead pipeline queries
    "lead_management": {
        "patterns": [
            r"(my |the |our )?(lead|leads) (pipeline|funnel|status)",
            r"how (are|is) (my |the |our )?(leads?|prospects?)",
            r"(lead|leads) (getting stuck|bottleneck|conversion)",
            r"where are (my |the |our )?(leads?|prospects?) (stuck|stalling)",
            r"(show|list|get) (my |the |our )?(new |hot )?(leads?|prospects?)",
            r"who (should|do) i (call|contact|reach out)",
            r"(lead|leads) coach(ing)?",
            r"(speed|time) to lead",
            r"lead (analytics?|metrics?|insights?)",
            r"(nurture|follow.?up) (leads?|list)",
        ],
        "intent": QueryIntent.LEAD_MANAGEMENT,
        "tools": ["lead_status_insights", "get_leads_by_status"],
        "urgency": "medium",
        "complexity": "moderate",
        "confidence": 0.95
    },

    # Loan pipeline queries
    "pipeline_status": {
        "patterns": [
            r"(my |the |our )?(loan|loans) (pipeline|funnel|status)",
            r"(show|what'?s? in) (my |the |our )?pipeline",
            r"how (are|is) (my |the |our )?(deals?|loans?|applications?)",
            r"(pipeline|funnel) (summary|update|status|overview)",
            r"(loans?|deals?) (in process|in progress|closing)",
            r"(closing|funded) (this week|today|soon)",
            r"what('?s| is) (in |my )?(pipeline|processing|underwriting)",
            r"(deals?|loans?) (at risk|stuck|delayed)",
            r"(pipeline|loan) (metrics?|analytics?|numbers?)",
        ],
        "intent": QueryIntent.PIPELINE_STATUS,
        "tools": ["get_pipeline", "get_pipeline_metrics"],
        "urgency": "medium",
        "complexity": "moderate",
        "confidence": 0.95
    },

    # Rate lock queries
    "market_intelligence": {
        "patterns": [
            r"should (i|we) (lock|float)",
            r"lock (or|vs|versus) float",
            r"(rate|rates) (recommendation|advice|guidance)",
            r"what('?s| is| are) (the |current )?(rate|rates|pricing)",
            r"(rate|rates|market) (today|right now|this week)",
            r"(lock|float) (recommendation|decision|advice)",
            r"(interest )?rate (lock|advisory|outlook)",
        ],
        "intent": QueryIntent.MARKET_INTELLIGENCE,
        "tools": ["get_rate_lock_advisory", "get_pipeline"],
        "urgency": "high",
        "complexity": "moderate",
        "confidence": 0.95
    },

    # Team performance queries
    "team_performance": {
        "patterns": [
            r"(my |our |team )?(performance|metrics|numbers|stats)",
            r"how (am i|are we|is the team) doing",
            r"(my |team )?scorecard",
            r"(production|volume) (report|summary|numbers)",
            r"(compare|comparison) (to |with )?(last month|benchmark)",
        ],
        "intent": QueryIntent.TEAM_PERFORMANCE,
        "tools": ["get_pipeline_metrics", "get_pipeline"],
        "urgency": "low",
        "complexity": "moderate",
        "confidence": 0.90
    },

    # Communication - Call requests
    "call_request": {
        "patterns": [
            r"(call|dial|phone|ring) (\+?1?[\d\-\.\s\(\)]{10,})",  # call + phone number
            r"(call|dial|phone|ring) (him|her|them|this person|the (client|borrower|lead))",
            r"(make|place|start|initiate) (a |the )?call",
            r"(can you |please )?(call|dial|phone|ring)",
            r"(click.?to.?dial|click.?to.?call)",
            r"(connect|get) me (on|with) (a )?call",
        ],
        "intent": QueryIntent.ACTION_REQUEST,
        "tools": ["click_to_dial"],
        "urgency": "high",
        "complexity": "simple",
        "confidence": 0.95,
        "requires_action": True
    },

    # Communication - SMS/Text requests
    "text_request": {
        "patterns": [
            r"(text|sms|message) (\+?1?[\d\-\.\s\(\)]{10,})",  # text + phone number
            r"(send|shoot) (a |an )?(text|sms|message)",
            r"(text|sms|message) (him|her|them|this person|the (client|borrower|lead))",
            r"(can you |please )?(text|sms|message)",
        ],
        "intent": QueryIntent.ACTION_REQUEST,
        "tools": ["send_sms"],
        "urgency": "medium",
        "complexity": "simple",
        "confidence": 0.95,
        "requires_action": True
    },
}


def extract_phone_number(query: str) -> Optional[str]:
    """Extract phone number from query text."""
    # Match various phone formats: (843) 834-4997, 843-834-4997, 8438344997, +1-843-834-4997
    phone_patterns = [
        r'\+?1?[\s.-]?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}',  # Standard US formats
        r'\b\d{10}\b',  # 10 digit number
    ]

    for pattern in phone_patterns:
        match = re.search(pattern, query)
        if match:
            # Clean the number - keep only digits
            number = re.sub(r'\D', '', match.group())
            if len(number) == 10:
                return number
            elif len(number) == 11 and number.startswith('1'):
                return number[1:]  # Remove leading 1
    return None


def pattern_match_intent(query: str) -> Optional[Dict[str, Any]]:
    """
    Fast pattern matching for common intents.
    Returns analysis dict if pattern matches, None otherwise.

    This can skip the LLM call entirely for well-known query patterns,
    saving ~5-7 seconds per request.
    """
    query_lower = query.lower().strip()

    for intent_key, config in INTENT_PATTERNS.items():
        for pattern in config["patterns"]:
            if re.search(pattern, query_lower, re.IGNORECASE):
                logger.info(f"[ANALYZE] FAST PATH: Pattern matched '{pattern}' -> {intent_key}")

                result = {
                    "intent": config["intent"],
                    "tools": config["tools"],
                    "urgency": config["urgency"],
                    "complexity": config["complexity"],
                    "confidence": config["confidence"],
                    "pattern_matched": pattern,
                    "fast_path": True,
                    "requires_action": config.get("requires_action", False)
                }

                # For call/text requests, extract phone number
                if intent_key in ["call_request", "text_request"]:
                    phone = extract_phone_number(query)
                    if phone:
                        result["extracted_entities"] = {"phone_number": phone}
                        logger.info(f"[ANALYZE] Extracted phone: {phone}")

                return result

    return None


def extract_entities(query: str) -> Dict[str, List]:
    """
    Simple entity extraction using regex patterns.
    Extracts loan IDs, names, amounts, dates, phone numbers, etc.
    """
    entities = {
        "loan_ids": [],
        "borrower_names": [],
        "amounts": [],
        "dates": [],
        "stages": [],
        "team_members": [],
        "phone_numbers": []
    }

    # Extract phone numbers
    phone = extract_phone_number(query)
    if phone:
        entities["phone_numbers"] = [phone]

    # Extract loan/lead IDs (numeric)
    id_matches = re.findall(r'\b(?:loan|lead|id|#)\s*(\d+)\b', query, re.IGNORECASE)
    if id_matches:
        entities["loan_ids"] = id_matches

    # Extract amounts
    amount_matches = re.findall(r'\$[\d,]+(?:\.\d{2})?|\b\d{3,}k?\b', query, re.IGNORECASE)
    if amount_matches:
        entities["amounts"] = amount_matches

    # Extract date references
    date_patterns = [
        r'\b(today|tomorrow|yesterday)\b',
        r'\b(this|next|last)\s+(week|month|quarter)\b',
        r'\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b',
    ]
    for pattern in date_patterns:
        matches = re.findall(pattern, query, re.IGNORECASE)
        if matches:
            entities["dates"].extend([m if isinstance(m, str) else ' '.join(m) for m in matches])

    # Extract stage mentions
    stages = ['new', 'disclosed', 'processing', 'submitted', 'underwriting',
              'approved', 'ctc', 'clear to close', 'docs out', 'funded']
    for stage in stages:
        if re.search(rf'\b{stage}\b', query, re.IGNORECASE):
            entities["stages"].append(stage)

    return entities


# =============================================================================
# LLM-BASED ANALYSIS (fallback for complex queries)
# =============================================================================

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

    OPTIMIZATION: Uses fast pattern matching first, falls back to LLM only if needed.
    - Pattern match: ~10ms (for 80%+ of common queries)
    - LLM fallback: ~5-7s (for complex/ambiguous queries)

    Args:
        state: Current agent state
        anthropic_client: Optional pre-configured Anthropic client

    Returns:
        Updated state with query analysis
    """
    state = add_node_trace(state, "analyze")
    node_start = time.time()

    try:
        user_message = state["user_message"]
        user_role = state.get("user_role", "loan_officer")

        # =================================================================
        # FAST PATH: Try pattern matching first (saves ~5-7 seconds)
        # =================================================================
        pattern_result = pattern_match_intent(user_message)

        if pattern_result:
            # Pattern matched - skip LLM entirely!
            entities = extract_entities(user_message)

            state = update_state(state, {
                "query_intent": pattern_result["intent"],
                "query_entities": entities,
                "query_urgency": pattern_result["urgency"],
                "query_complexity": pattern_result["complexity"],
                "required_tools": pattern_result["tools"],
                "requires_action": False,
                "analysis_method": "pattern_match"
            })

            node_time = (time.time() - node_start) * 1000
            logger.info(
                f"[ANALYZE] ⚡ FAST PATH complete in {node_time:.0f}ms | "
                f"intent={pattern_result['intent'].value}, tools={pattern_result['tools']}, "
                f"pattern='{pattern_result['pattern_matched']}'"
            )

            return state

        # =================================================================
        # SLOW PATH: Use LLM for complex/ambiguous queries
        # =================================================================
        logger.info(f"[ANALYZE] No pattern match, falling back to LLM analysis")

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

        llm_start = time.time()
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
        llm_time = (time.time() - llm_start) * 1000
        logger.info(f"[ANALYZE] ⏱️ LLM call took {llm_time:.0f}ms (system prompt: {len(system_prompt)} chars)")

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
            "requires_action": analysis.get("requires_action", False),
            "analysis_method": "llm"
        })

        node_time = (time.time() - node_start) * 1000
        logger.info(f"[ANALYZE] ⏱️ Total node time: {node_time:.0f}ms | intent={intent.value}, tools={required_tools}")

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
            "required_tools": ["get_daily_priorities", "get_tasks", "get_pipeline"],
            "requires_action": False,
            "analysis_method": "fallback"
        })

    except Exception as e:
        logger.error(f"Query analysis failed: {e}")
        state = add_error(state, f"Query analysis error: {str(e)}")
        return update_state(state, {
            "query_intent": QueryIntent.TASK_MANAGEMENT,
            "required_tools": ["get_daily_priorities", "get_tasks", "get_pipeline"],
            "requires_action": False,
            "analysis_method": "fallback"
        })
