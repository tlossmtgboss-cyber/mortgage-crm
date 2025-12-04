"""
Query Analyzer Node (OPTIMIZED v3)

This node analyzes the user's query to determine:
- Intent classification (via intent_router for agent selection)
- Entity extraction
- Required tools (scoped to 1-2 relevant agents, not all 160)
- Urgency and complexity assessment

OPTIMIZATION v3: Intent-based agent routing
- Ultra-fast pattern matching: ~1-5ms for 80%+ of queries
- Falls back to Haiku LLM: ~500-1000ms for complex queries
- Loads only 8-16 tools per request instead of all 160

Performance:
- v1 (original): All tools, 5-7s LLM call
- v2 (pattern match): 10ms pattern, 5-7s LLM fallback
- v3 (intent router): 1-5ms pattern, 500-1000ms Haiku fallback, scoped tools
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
from ..intent_router import (
    classify_intent,
    get_tools_for_intent,
    INTENT_TO_AGENTS
)

logger = logging.getLogger(__name__)

# Base tools always available (core CRM functions)
# These are the service.py tools that work regardless of agent
BASE_TOOLS = [
    # Pipeline & Loan Tools
    "get_pipeline",
    "search_loans",
    "search_leads",
    "get_pipeline_metrics",

    # Lead Intelligence
    "lead_status_insights",
    "get_leads_by_status",

    # Task Management
    "get_tasks",
    "create_task",
    "get_daily_priorities",

    # Market Intelligence
    "get_rate_lock_advisory",

    # Communication
    "click_to_dial",
    "make_call",
    "send_sms",
    "send_text",
]

# Map intents to the base tools that support them
INTENT_TO_BASE_TOOLS: Dict[str, List[str]] = {
    "priorities": ["get_daily_priorities", "get_tasks", "get_pipeline"],
    "tasks": ["get_tasks", "create_task", "get_daily_priorities"],
    "leads": ["lead_status_insights", "get_leads_by_status", "search_leads"],
    "pipeline": ["get_pipeline", "get_pipeline_metrics", "search_loans"],
    "rates": ["get_rate_lock_advisory", "get_pipeline"],
    "calls": ["click_to_dial", "make_call", "search_leads"],
    "email": ["search_leads", "search_loans"],  # Basic for now
    "schedule": ["get_tasks", "get_daily_priorities"],  # Basic for now
    "documents": ["search_loans", "get_pipeline"],  # Basic for now
    "compliance": ["search_loans", "get_pipeline"],  # Basic for now
    "sla": ["get_pipeline", "get_pipeline_metrics"],  # Basic for now
    "reports": ["get_pipeline_metrics", "get_pipeline"],
    "coaching": ["get_pipeline_metrics", "get_pipeline"],
    "customer": ["search_leads", "search_loans"],
    "general": ["get_daily_priorities", "get_pipeline", "get_tasks"],
}

# Legacy: Keep AVAILABLE_TOOLS for backwards compatibility
AVAILABLE_TOOLS = BASE_TOOLS


# =============================================================================
# FAST PATTERN MATCHING (skip LLM for common queries)
# =============================================================================

INTENT_PATTERNS = {
    # Greetings - fastest path, use Haiku model
    "greeting": {
        "patterns": [
            r"^(hi|hey|hello|howdy|yo|sup)(\s+there)?!?$",  # hi, hi there, hey there, etc.
            r"^(hi|hey|hello|howdy)[\s,!]*$",  # hi!, hello,, etc.
            r"^(good\s*)?(morning|afternoon|evening)!?$",
            r"^what'?s? up\??$",
            r"^how are you\??$",
            r"^how'?s? it going\??$",
            r"^greetings!?$",
        ],
        "intent": QueryIntent.GENERAL_QUERY,  # Map to GENERAL_QUERY for state
        "intent_str": "greeting",  # But use this for model selection
        "tools": [],  # No tools needed for greetings
        "urgency": "low",
        "complexity": "simple",
        "confidence": 0.99,
        "use_haiku": True  # Flag to use fast Haiku model
    },

    # Simple queries - use Haiku model
    "simple": {
        "patterns": [
            r"^(thanks?|thank you)!?$",
            r"^(ok|okay|got it|sounds good|perfect)!?$",
            r"^(yes|no|yep|nope|sure|maybe)!?$",
            r"^(bye|goodbye|see you|later)!?$",
            r"^what (can|do) you do\??$",
            r"^help( me)?\??$",
        ],
        "intent": QueryIntent.GENERAL_QUERY,
        "intent_str": "simple",
        "tools": ["get_daily_priorities"],  # Minimal tools
        "urgency": "low",
        "complexity": "simple",
        "confidence": 0.99,
        "use_haiku": True
    },

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
                    "intent_str": config.get("intent_str", intent_key),  # For Haiku model selection
                    "tools": config["tools"],
                    "urgency": config["urgency"],
                    "complexity": config["complexity"],
                    "confidence": config["confidence"],
                    "pattern_matched": pattern,
                    "fast_path": True,
                    "requires_action": config.get("requires_action", False),
                    "use_haiku": config.get("use_haiku", False)  # Flag for fast Haiku model
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

    OPTIMIZATION v3: Intent-based routing with timing logs
    - Fast pattern match: ~1-5ms (handles 80%+ of queries)
    - Intent router: ~1-5ms pattern, ~500-1000ms Haiku fallback
    - Scoped tools: Only loads 2-4 tools per intent instead of all

    Args:
        state: Current agent state
        anthropic_client: Optional pre-configured Anthropic client

    Returns:
        Updated state with query analysis
    """
    state = add_node_trace(state, "analyze")
    node_start = time.time()
    timing = {}  # Track timing for each step

    try:
        user_message = state["user_message"]
        user_role = state.get("user_role", "loan_officer")

        logger.info(f"[ANALYZE] ========== START ==========")
        logger.info(f"[ANALYZE] Query: '{user_message[:100]}{'...' if len(user_message) > 100 else ''}'")

        # =================================================================
        # STEP 1: Fast pattern matching for common intents (~1-5ms)
        # =================================================================
        pattern_start = time.time()
        pattern_result = pattern_match_intent(user_message)
        timing["pattern_match"] = (time.time() - pattern_start) * 1000

        if pattern_result:
            # Pattern matched - use legacy path for now (already optimized)
            entities = extract_entities(user_message)

            # Merge extracted_entities from pattern matching (e.g., phone numbers)
            if pattern_result.get("extracted_entities"):
                entities.update(pattern_result["extracted_entities"])

            # Map legacy intent to new intent for agent selection
            intent_str = pattern_result["intent"].value.lower()

            # Get scoped tools for this intent
            scoped_tools = INTENT_TO_BASE_TOOLS.get(intent_str, INTENT_TO_BASE_TOOLS["general"])

            # Use pattern-determined tools if more specific
            final_tools = pattern_result["tools"] if pattern_result["tools"] else scoped_tools

            state = update_state(state, {
                "query_intent": pattern_result["intent"],
                "query_entities": entities,
                "extracted_entities": pattern_result.get("extracted_entities", {}),
                "query_urgency": pattern_result["urgency"],
                "query_complexity": pattern_result["complexity"],
                "required_tools": final_tools,
                "requires_action": pattern_result.get("requires_action", False),
                "analysis_method": "pattern_match",
                "intent_agents": INTENT_TO_AGENTS.get(intent_str, ["pipeline_analyst"]),
            })

            node_time = (time.time() - node_start) * 1000
            logger.info(
                f"[ANALYZE] ⚡ FAST PATH complete in {node_time:.1f}ms | "
                f"pattern_match={timing['pattern_match']:.1f}ms | "
                f"intent={pattern_result['intent'].value}, tools={final_tools}"
            )
            logger.info(f"[ANALYZE] ========== END (pattern_match) ==========")

            return state

        # =================================================================
        # STEP 2: Use intent router for classification (~1-5ms pattern, ~500-1000ms LLM)
        # =================================================================
        logger.info(f"[ANALYZE] No legacy pattern match, using intent router")

        intent_start = time.time()
        intent_result = await classify_intent(user_message, anthropic_client)
        timing["intent_classify"] = intent_result.get("elapsed_ms", (time.time() - intent_start) * 1000)

        intent_str = intent_result["intent"]
        confidence = intent_result["confidence"]
        agents = intent_result["agents"]
        method = intent_result["method"]

        logger.info(
            f"[ANALYZE] Intent: {intent_str} (conf={confidence:.2f}) | "
            f"agents={agents} | method={method} | time={timing['intent_classify']:.1f}ms"
        )

        # =================================================================
        # STEP 3: Get scoped tools for this intent
        # =================================================================
        tools_start = time.time()
        scoped_tools = INTENT_TO_BASE_TOOLS.get(intent_str, INTENT_TO_BASE_TOOLS["general"])
        timing["tool_scope"] = (time.time() - tools_start) * 1000

        logger.info(f"[ANALYZE] Scoped tools ({len(scoped_tools)}): {scoped_tools}")

        # =================================================================
        # STEP 4: Extract entities
        # =================================================================
        entity_start = time.time()
        entities = extract_entities(user_message)
        timing["entity_extract"] = (time.time() - entity_start) * 1000

        # Map intent string to QueryIntent enum
        intent_map = {
            "pipeline": QueryIntent.PIPELINE_STATUS,
            "leads": QueryIntent.LEAD_MANAGEMENT,
            "coaching": QueryIntent.TEAM_PERFORMANCE,
            "tasks": QueryIntent.TASK_MANAGEMENT,
            "priorities": QueryIntent.TASK_MANAGEMENT,
            "calls": QueryIntent.COMMUNICATION,
            "email": QueryIntent.COMMUNICATION,
            "documents": QueryIntent.DOCUMENT_ANALYSIS,
            "rates": QueryIntent.MARKET_INTELLIGENCE,
            "reports": QueryIntent.FINANCIAL_ANALYSIS,
            "sla": QueryIntent.PIPELINE_STATUS,
            "schedule": QueryIntent.TASK_MANAGEMENT,
            "compliance": QueryIntent.DOCUMENT_ANALYSIS,
            "video": QueryIntent.COMMUNICATION,
            "billing": QueryIntent.GENERAL_QUERY,
            "customer": QueryIntent.LEAD_MANAGEMENT,
            "integrations": QueryIntent.GENERAL_QUERY,
            "general": QueryIntent.GENERAL_QUERY,
        }

        query_intent = intent_map.get(intent_str, QueryIntent.GENERAL_QUERY)

        # Determine if action is required
        action_intents = ["calls", "email", "schedule"]
        requires_action = intent_str in action_intents

        # Determine urgency based on intent
        urgency_map = {
            "priorities": "high",
            "calls": "high",
            "rates": "high",
            "sla": "high",
            "leads": "medium",
            "pipeline": "medium",
            "tasks": "medium",
            "general": "low",
        }

        # Update state with analysis results
        # Check if this is a Haiku-eligible intent (greeting, simple)
        use_haiku = intent_str in ["greeting", "simple"]

        state = update_state(state, {
            "query_intent": query_intent,
            "query_entities": entities,
            "extracted_entities": {},
            "query_urgency": urgency_map.get(intent_str, "medium"),
            "query_complexity": "simple" if confidence > 0.8 else "moderate",
            "required_tools": scoped_tools,
            "requires_action": requires_action,
            "analysis_method": f"intent_router_{method}",
            "intent_agents": agents,
            "intent_confidence": confidence,
            "use_haiku": use_haiku,  # Flag for Haiku model selection
            "intent_str": intent_str,  # String intent for model selection
        })

        node_time = (time.time() - node_start) * 1000
        logger.info(
            f"[ANALYZE] ⏱️ TIMING BREAKDOWN:\n"
            f"  - pattern_match: {timing.get('pattern_match', 0):.1f}ms\n"
            f"  - intent_classify: {timing.get('intent_classify', 0):.1f}ms\n"
            f"  - tool_scope: {timing.get('tool_scope', 0):.1f}ms\n"
            f"  - entity_extract: {timing.get('entity_extract', 0):.1f}ms\n"
            f"  - TOTAL: {node_time:.1f}ms"
        )
        model_hint = "HAIKU (fast)" if use_haiku else "SONNET (full)"
        logger.info(f"[ANALYZE] Model selection: {model_hint} | intent_str={intent_str}")
        logger.info(f"[ANALYZE] ========== END (intent_router) ==========")

        return state

    except Exception as e:
        logger.error(f"[ANALYZE] Query analysis failed: {e}", exc_info=True)
        state = add_error(state, f"Query analysis error: {str(e)}")

        node_time = (time.time() - node_start) * 1000
        logger.info(f"[ANALYZE] ========== END (fallback, {node_time:.1f}ms) ==========")

        return update_state(state, {
            "query_intent": QueryIntent.TASK_MANAGEMENT,
            "query_entities": {},
            "query_urgency": "medium",
            "query_complexity": "moderate",
            "required_tools": ["get_daily_priorities", "get_tasks", "get_pipeline"],
            "requires_action": False,
            "analysis_method": "fallback",
            "intent_agents": ["pipeline_analyst", "task_automation"],
        })
