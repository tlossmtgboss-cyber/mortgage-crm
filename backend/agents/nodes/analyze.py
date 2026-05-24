"""
Query Analyzer Node (OPTIMIZED v3)

This node analyzes the user's query to determine:
- Intent classification (via intent_router for agent selection)
- Entity extraction
- Required tools (scoped to 1-2 relevant agents, not all 160)
- Urgency and complexity assessment
- User memory retrieval (preferences, directives, context)

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
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from ..anthropic_client import get_anthropic_client
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
    INTENT_TO_AGENTS,
    HAIKU_INTENTS,
    is_haiku_intent,
    _resolve_agents_for_intent,
)

try:
    from utils.pii_mask import mask_phone
except ImportError:
    mask_phone = lambda x: x[:3] + "***" + x[-2:] if x and len(x) > 5 else "***"


def _resolve_consolidated_agents(intent_str: str) -> list:
    """Resolve intent to consolidated agent IDs, with legacy fallback."""
    return _resolve_agents_for_intent(intent_str)

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
    "get_top_leads",
    "get_stale_leads",

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
    "send_email",
    "bulk_lead_outreach",  # Bulk outreach to leads with scheduling
]

# Single source of truth for intent→tool mapping lives in intent_router.py
from ..intent_router import INTENT_TO_SCOPED_TOOLS
INTENT_TO_BASE_TOOLS = INTENT_TO_SCOPED_TOOLS

# Legacy: Keep AVAILABLE_TOOLS for backwards compatibility
AVAILABLE_TOOLS = BASE_TOOLS


# =============================================================================
# MEMORY RETRIEVAL (query AgentMemory for user preferences/context)
# =============================================================================

def _score_memory_relevance(memory_value: str, query: str) -> float:
    """
    Score how relevant a memory is to the current query using keyword overlap.

    Returns a float between 0.0 and 1.0.  Directives and preferences get a
    base relevance boost since they should almost always be injected.
    """
    if not query or not memory_value:
        return 0.0

    # Tokenize into lowercase words, stripping common noise
    _stop_words = {"the", "a", "an", "is", "are", "was", "were", "to", "for",
                   "and", "or", "of", "in", "on", "at", "my", "i", "me", "it"}
    query_words = {w for w in query.lower().split() if w not in _stop_words and len(w) > 2}
    memory_words = {w for w in memory_value.lower().split() if w not in _stop_words and len(w) > 2}

    if not query_words or not memory_words:
        return 0.0

    overlap = query_words & memory_words
    # Jaccard-like score: overlap / smaller set
    score = len(overlap) / min(len(query_words), len(memory_words)) if memory_words else 0.0
    return min(score, 1.0)


def _cosine_similarity(a: list, b: list) -> float:
    """
    Compute cosine similarity between two embedding vectors using numpy.

    Returns a float between -1.0 and 1.0 (typically 0.0-1.0 for normalized
    OpenAI embeddings).  Returns 0.0 on any error.
    """
    try:
        import numpy as np
        a_arr = np.asarray(a, dtype=np.float32)
        b_arr = np.asarray(b, dtype=np.float32)
        denom = np.linalg.norm(a_arr) * np.linalg.norm(b_arr)
        if denom < 1e-10:
            return 0.0
        return float(np.dot(a_arr, b_arr) / denom)
    except Exception:
        return 0.0


async def _generate_query_embedding(query_text: str) -> Optional[list]:
    """
    Generate an embedding for the user query using the same model as
    retrieval_service (text-embedding-3-small).

    Returns None on failure so callers fall back to keyword-only scoring.
    """
    try:
        from services.aria_memory.embedding_service import generate_embedding_async
        return await generate_embedding_async(query_text)
    except Exception as e:
        logger.debug(f"[ANALYZE] Query embedding generation failed: {e}")
        return None


async def _retrieve_user_memories(user_id: str, organization_id: Optional[int], current_query: str = "") -> tuple:
    """
    Query AgentMemory table for the current user's stored memories.

    Uses hybrid keyword + semantic scoring:
    - Keyword relevance: Jaccard-style word overlap (always available)
    - Semantic relevance: cosine similarity of embeddings (when available)

    Scoring formula per memory:
    - WITH embedding:  0.25*confidence + 0.30*semantic + 0.25*keyword + 0.20*type_boost
    - WITHOUT embedding: 0.40*confidence + 0.40*keyword + 0.20*type_boost  (legacy)

    Applies TTL filtering (expired memories excluded), then ranks by
    combined score.  Returns the top 10 most relevant memories.

    Returns:
        Tuple of (memories_list, formatted_memory_context_string).
        On failure, returns ([], "").
    """
    try:
        # Lazy imports to avoid circular dependencies
        from db import SessionLocal
        from database.models.agent_memory import AgentMemory, MemoryType

        db = SessionLocal()
        try:
            if organization_id is not None:
                from sqlalchemy import text as sa_text
                db.execute(sa_text("SET LOCAL app.current_tenant = :tid"), {"tid": str(organization_id)})

            now = datetime.now(timezone.utc)

            # Query PREFERENCE, DIRECTIVE, CONTEXT, and FACT memories
            query = (
                db.query(AgentMemory)
                .filter(
                    AgentMemory.user_id == int(user_id) if str(user_id).isdigit() else AgentMemory.user_id == user_id,
                    AgentMemory.memory_type.in_([
                        MemoryType.PREFERENCE,
                        MemoryType.DIRECTIVE,
                        MemoryType.CONTEXT,
                        MemoryType.FACT,
                    ]),
                )
            )

            # Tenant isolation
            if organization_id is not None:
                query = query.filter(AgentMemory.organization_id == organization_id)

            # Exclude expired memories (TTL filtering)
            query = query.filter(
                (AgentMemory.expires_at.is_(None)) | (AgentMemory.expires_at > now)
            )

            query = query.filter(AgentMemory.superseded_by.is_(None))

            # Fetch a broader pool so we can re-rank by relevance
            memories_rows = (
                query
                .order_by(AgentMemory.confidence.desc())
                .limit(50)
                .all()
            )

            if not memories_rows:
                return [], ""

            # Generate query embedding ONCE for semantic scoring.
            # Only attempt if at least one memory has an embedding
            # (avoids wasting an API call when the DB has no embeddings).
            query_embedding = None
            has_any_embedding = any(
                getattr(mem, "embedding", None) is not None for mem in memories_rows
            )
            if current_query and has_any_embedding:
                query_embedding = await _generate_query_embedding(current_query)

            semantic_hit_count = 0

            # Build candidate list with hybrid relevance scoring
            candidates = []
            for mem in memories_rows:
                mem_type = mem.memory_type.value if hasattr(mem.memory_type, 'value') else str(mem.memory_type)
                confidence = mem.confidence or 0.5

                # Keyword relevance (always computed)
                keyword_relevance = _score_memory_relevance(mem.value or "", current_query)

                # Semantic relevance (only when both query and memory have embeddings)
                mem_embedding = getattr(mem, "embedding", None)
                semantic_relevance = 0.0
                has_semantic = False

                if query_embedding is not None and mem_embedding is not None:
                    # pgvector returns embeddings as lists; compute cosine sim
                    sim = _cosine_similarity(query_embedding, list(mem_embedding))
                    # Clamp to [0, 1] — OpenAI normalized embeddings rarely go negative
                    semantic_relevance = max(0.0, min(sim, 1.0))
                    has_semantic = True
                    semantic_hit_count += 1

                # Directives and preferences get a base relevance boost —
                # they should almost always be injected regardless of query
                type_boost = 0.0
                if mem_type in ("directive", "preference"):
                    type_boost = 0.4

                # Combined score depends on whether semantic signal is available
                if has_semantic:
                    # Hybrid: 25% confidence + 30% semantic + 25% keyword + 20% type boost
                    combined_score = (
                        0.25 * confidence
                        + 0.30 * semantic_relevance
                        + 0.25 * keyword_relevance
                        + 0.20 * min(type_boost + keyword_relevance, 1.0)
                    )
                else:
                    # Keyword-only fallback: 40% confidence + 40% keyword + 20% type boost
                    combined_score = (
                        0.40 * confidence
                        + 0.40 * keyword_relevance
                        + 0.20 * min(type_boost + keyword_relevance, 1.0)
                    )

                candidates.append({
                    "id": mem.id,
                    "type": mem_type,
                    "key": mem.key,
                    "value": mem.value,
                    "confidence": confidence,
                    "keyword_relevance": keyword_relevance,
                    "semantic_relevance": semantic_relevance if has_semantic else None,
                    "combined_score": combined_score,
                })

            # Sort by combined score descending, take top 10
            candidates.sort(key=lambda c: c["combined_score"], reverse=True)
            memories_list = candidates[:10]

            # Format for prompt injection
            lines = []
            for m in memories_list:
                lines.append(f"[{m['type'].upper()}] {m['value']} (confidence: {m['confidence']:.1f})")
            formatted = "\n".join(lines)

            scoring_mode = (
                f"hybrid ({semantic_hit_count}/{len(candidates)} with embeddings)"
                if semantic_hit_count > 0
                else "keyword-only"
            )
            logger.info(
                f"[ANALYZE] Retrieved {len(memories_list)} memories (from {len(candidates)} candidates, "
                f"scoring={scoring_mode}) for user {user_id}"
            )
            return memories_list, formatted

        finally:
            db.close()

    except Exception as e:
        logger.warning(f"[ANALYZE] Memory retrieval failed (graceful degradation): {e}")
        return [], ""


async def _retrieve_vector_context(user_id: str, user_message: str) -> str:
    """
    If Pinecone/ai_memory_service is available, retrieve semantically
    relevant context for the current message.

    Returns formatted context string, or "" on failure.

    This is an async function because it is always called from the async
    analyze_query node within the LangGraph workflow. The Pinecone service's
    retrieve_relevant_context is declared async but performs synchronous I/O
    internally, so we run it in a thread executor when needed to avoid
    blocking the event loop.
    """
    try:
        from integrations.pinecone_service import vector_memory

        if not vector_memory or not vector_memory.enabled:
            return ""

        import asyncio

        def _sync_fetch():
            """Run the Pinecone query synchronously in a thread."""
            # The vector_memory.retrieve_relevant_context is async but uses
            # sync Pinecone client internally. Create a fresh event loop in
            # the thread to await it.
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(
                    vector_memory.retrieve_relevant_context(
                        user_id=int(user_id) if str(user_id).isdigit() else user_id,
                        current_query=user_message,
                        top_k=3,
                    )
                )
            finally:
                loop.close()

        # Always run in a thread executor so we never block the event loop
        # and don't conflict with the already-running loop
        try:
            loop = asyncio.get_running_loop()
            results = await loop.run_in_executor(None, _sync_fetch)
        except RuntimeError:
            # No running loop (unexpected, but handle gracefully)
            results = asyncio.run(
                vector_memory.retrieve_relevant_context(
                    user_id=int(user_id) if str(user_id).isdigit() else user_id,
                    current_query=user_message,
                    top_k=3,
                )
            )

        if not results:
            return ""

        parts = []
        for ctx in results[:3]:
            text = ctx.get("metadata", {}).get("text", ctx.get("text", ""))
            if text:
                parts.append(text[:200])

        if parts:
            formatted = "\n".join(f"- {p}" for p in parts)
            logger.info(f"[ANALYZE] Retrieved {len(parts)} vector context items for user {user_id}")
            return formatted

        return ""

    except Exception as e:
        logger.debug(f"[ANALYZE] Vector context retrieval skipped: {e}")
        return ""


# =============================================================================
# FAST PATTERN MATCHING (skip LLM for common queries)
# =============================================================================

INTENT_PATTERNS = {
    # Greetings - fastest path, use Haiku model
    "greeting": {
        "patterns": [
            r"^(hi|hey|hello|howdy|yo|sup)(\s+there)?(\s+\w+)?[!,.\s]*$",  # hi, hi there, hey there friend, etc.
            r"^(hi|hey|hello|howdy)[!,.\s]*$",  # hi!, hello,, etc.
            r"^(good\s*)?(morning|afternoon|evening)[!,.\s]*$",
            r"^what'?s? up\??[!,.\s]*$",
            r"^how are you\??[!,.\s]*$",
            r"^how'?s? it going\??[!,.\s]*$",
            r"^greetings[!,.\s]*$",
            r"^howdy\s+\w+[!,.\s]*$",  # howdy partner, howdy friend, etc.
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
            # Call list queries - "what calls do I need to make today?"
            r"what (calls?|people) (do i |should i |to )?(need to )?(make|call|contact)( today)?",
            r"who (do i |should i )?need to (call|contact|reach out to)( today)?",
            r"(my |today'?s? )?call (list|queue)",
            r"calls? (i need|to make)( today)?",
        ],
        "intent": QueryIntent.TASK_MANAGEMENT,
        "tools": ["get_daily_priorities", "get_tasks", "lead_status_insights"],
        "urgency": "high",
        "complexity": "simple",
        "confidence": 0.95
    },

    # Lead pipeline queries
    # Top leads queries - highest priority for immediate calling
    "top_leads": {
        "patterns": [
            r"(get|show|give|list) (me )?(my |the )?(top|best|highest|hot|priority) ?\d* ?(leads?|prospects?)",
            r"(my |the )?(top|best|highest|hot) ?\d* ?(leads?|prospects?) (to call|for calling|with phone)",
            r"call (my |the )?(top|best|hot|warm|priority|highest)( \d+)? (leads?|prospects?)",
            r"(top|best|hot|priority) \d+ (leads?|contacts?|prospects?)",
            r"who (should|do|can) i call (first|next|today)",
            r"(leads?|prospects?) (with |that have )?(phone|contact) (numbers?|info)",
        ],
        "intent": QueryIntent.LEAD_MANAGEMENT,
        "tools": ["get_top_leads"],  # Only use get_top_leads for these queries
        "urgency": "high",
        "complexity": "simple",
        "confidence": 0.98
    },

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
            # General lead calling without specific "top" keyword
            r"(call|contact|reach out to) (my |the )?(leads?|prospects?)",
            # Contact frequency patterns - leads not contacted recently
            r"(leads?|prospects?) (not |haven't been |i haven't )?contacted",
            r"(haven't|have not|not) contacted",
            r"(stale|inactive|cold|dormant) (leads?|prospects?)",
            r"last contact(ed)?",
            r"(not )?(contacted|reached) in \d+ (days?|weeks?)",
            r"overdue (for )?contact",
            r"(leads?|prospects?) (need(s|ing)?|require) follow.?up",
        ],
        "intent": QueryIntent.LEAD_MANAGEMENT,
        "tools": ["lead_status_insights", "get_leads_by_status", "get_top_leads", "get_stale_leads"],
        "urgency": "medium",
        "complexity": "moderate",
        "confidence": 0.95
    },

    # Borrower-specific queries - HIGHEST PRIORITY for data boundaries
    # Must come before general pipeline queries to ensure proper filtering
    "borrower_specific": {
        "patterns": [
            r"(insights?|info|information|details?|update|status) (on|about|for) (borrower |client |customer )?[A-Z][a-z]+",  # insights on borrower Thompson
            r"(borrower|client|customer|applicant) [A-Z][a-z]+",  # borrower Thompson
            r"[A-Z][a-z]+'?s? (loan|file|application|deal|status)",  # Thompson's loan
            r"(show|give|get|tell) me (about |info on )?[A-Z][a-z]+'?s?",  # show me about Thompson
            r"(how is|what about|update on) [A-Z][a-z]+",  # how is Thompson
            r"(find|search|look up) (borrower |client )?[A-Z][a-z]+",  # find borrower Thompson
        ],
        "intent": QueryIntent.PIPELINE_STATUS,
        "tools": ["search_loans"],  # Use search_loans with the borrower name filter
        "urgency": "medium",
        "complexity": "simple",
        "confidence": 0.95,
        "extract_borrower_name": True  # Flag to extract name as search query
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

    # Historical comparisons - Q3 vs Q4, month-over-month, year-over-year
    # MUST come before team_performance to catch "compare Q3 to Q4" type queries
    "historical": {
        "patterns": [
            r"q[1-4]\s*(\d{4})?\s*(vs?\.?|versus|to|compared? to?)\s*q[1-4]",  # Q3 vs Q4, Q1 2025 to Q2 2025
            r"compare\s*(q[1-4]|january|february|march|april|may|june|july|august|september|october|november|december)",
            r"(q[1-4])\s*(\d{4})?\s*(performance|metrics|results|numbers)",  # Q3 2025 performance
            r"(last|previous|this)\s*(month|quarter|year)\s*(vs?\.?|versus|compared? to?|to)",
            r"(month|quarter|year)\s*over\s*(month|quarter|year)",
            r"(january|february|march|april|may|june|july|august|september|october|november|december)\s*(\d{4})?\s*(vs?\.?|to|versus)",
            r"(ytd|year to date)\s*(performance|comparison|metrics)",
            r"how did (q[1-4]|january|february|march|april|may|june|july|august|september|october|november|december) (do|perform)",
            r"(performance|results|metrics) (for|in|during) (q[1-4]|january|february|march|april|may|june|july|august|september|october|november|december)",
            r"historical (comparison|data|performance|metrics)",
            r"(what|how much) data (do we|is) (have|available)",
            r"when does (our|my) data (start|begin)",
        ],
        "intent": QueryIntent.FINANCIAL_ANALYSIS,  # Map to financial analysis for historical reports
        "intent_str": "historical",  # Used for intent routing
        "tools": ["get_performance_by_period", "compare_periods", "get_data_availability"],
        "urgency": "low",
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

    # Communication - Bulk outreach to leads
    "bulk_lead_outreach": {
        "patterns": [
            r"(send|text|sms|message).*(all|every|each).*(lead|new lead|prospect)",  # send text to all leads
            r"(text|sms|message|reach out).*(all|my).*(new|hot|cold|stale)?\s*(lead|prospect)",  # text all my new leads
            r"(bulk|mass) (text|sms|outreach|message)",  # bulk text
            r"(schedule|set up).*(call|meeting).*(with|for).*(all|every|each).*(lead)",  # schedule calls with all leads
        ],
        "intent": QueryIntent.ACTION_REQUEST,
        "tools": ["bulk_lead_outreach", "get_leads_by_status", "send_sms"],
        "urgency": "medium",
        "complexity": "complex",
        "confidence": 0.90,
        "requires_action": True
    },

    # Communication - Email requests
    "email_request": {
        "patterns": [
            r"(send|shoot|fire off|draft) (a |an )?email",  # send an email
            r"email ([\w\.\-]+@[\w\.\-]+)",  # email user@example.com
            r"(send|email) (him|her|them|this person|the (client|borrower|lead)) (an )?email",
            r"(can you |please )?(send|write|draft) (a |an )?email",
            r"send (a |an )?email to",  # send email to...
            r"email (to|about|regarding)",  # email to/about
        ],
        "intent": QueryIntent.ACTION_REQUEST,
        "tools": ["send_email"],
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


def extract_email_address(query: str) -> Optional[str]:
    """Extract email address from query text."""
    email_pattern = r'[\w\.\-\+]+@[\w\.\-]+\.\w+'
    match = re.search(email_pattern, query)
    if match:
        return match.group()
    return None


def extract_borrower_name(query: str) -> Optional[str]:
    """Extract borrower name from query text for search_loans filtering."""
    # Patterns to extract proper nouns that are likely borrower names
    name_patterns = [
        r'(?:borrower|client|customer|applicant)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)',  # borrower Thompson
        r'(?:insights?|info|information|details?|update|status)\s+(?:on|about|for)\s+(?:borrower\s+|client\s+|customer\s+)?([A-Z][a-z]+)',  # insights on Thompson
        r'([A-Z][a-z]+)\'?s?\s+(?:loan|file|application|deal|status)',  # Thompson's loan
        r'(?:show|give|get|tell)\s+me\s+(?:about\s+|info\s+on\s+)?([A-Z][a-z]+)',  # show me about Thompson
        r'(?:how\s+is|what\s+about|update\s+on)\s+([A-Z][a-z]+)',  # how is Thompson
        r'(?:find|search|look\s+up)\s+(?:borrower\s+|client\s+)?([A-Z][a-z]+)',  # find Thompson
    ]

    # Common words that should not be treated as names
    common_words = {
        'Show', 'Give', 'Get', 'Tell', 'What', 'How', 'The', 'My', 'Our', 'This', 'That',
        'Pipeline', 'Loan', 'Lead', 'Task', 'Rate', 'Status', 'Update', 'Info', 'Details',
        'Today', 'Tomorrow', 'Yesterday', 'Week', 'Month', 'Year', 'Insights', 'About'
    }

    for pattern in name_patterns:
        match = re.search(pattern, query)
        if match:
            name = match.group(1)
            if name not in common_words:
                logger.info(f"[ANALYZE] Extracted borrower name: {name}")
                return name
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
                        logger.info(f"[ANALYZE] Extracted phone: {mask_phone(phone)}")

                # For email requests, extract email address
                if intent_key == "email_request":
                    email = extract_email_address(query)
                    if email:
                        result["extracted_entities"] = result.get("extracted_entities", {})
                        result["extracted_entities"]["email_address"] = email
                        logger.info(f"[ANALYZE] Extracted email: {email}")

                # For borrower-specific queries, extract the borrower name
                if config.get("extract_borrower_name"):
                    borrower_name = extract_borrower_name(query)
                    if borrower_name:
                        result["extracted_entities"] = result.get("extracted_entities", {})
                        result["extracted_entities"]["borrower_name"] = borrower_name
                        result["extracted_entities"]["search_query"] = borrower_name  # For search_loans tool
                        logger.info(f"[ANALYZE] Extracted borrower name for search: {borrower_name}")

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
        "phone_numbers": [],
        "email_addresses": []
    }

    # Extract phone numbers
    phone = extract_phone_number(query)
    if phone:
        entities["phone_numbers"] = [phone]

    # Extract email addresses
    email = extract_email_address(query)
    if email:
        entities["email_addresses"] = [email]

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

    # Extract borrower names - look for patterns like "borrower Thompson", "client Smith", etc.
    # Also detect proper nouns after trigger words
    name_patterns = [
        r'(?:borrower|client|customer|applicant|person|for)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)',  # borrower Thompson
        r'(?:about|on|for|update on)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s*(?:\'s)?\s*(?:loan|file|application|deal)?',  # about Thompson's loan
        r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s*(?:\'s)?\s+(?:loan|file|application|status|deal)\b',  # Thompson's loan
    ]
    for pattern in name_patterns:
        matches = re.findall(pattern, query)
        if matches:
            # Filter out common non-name words
            common_words = {'New', 'Show', 'Give', 'Get', 'What', 'How', 'The', 'My', 'Our', 'This', 'That'}
            names = [m for m in matches if m not in common_words]
            if names:
                entities["borrower_names"].extend(names)
                break  # Only use first matching pattern to avoid duplicates

    return entities


# =============================================================================
# LLM-BASED ANALYSIS (fallback for complex queries)
# =============================================================================

ANALYZE_SYSTEM_PROMPT = """Query analyzer for mortgage CRM. Return ONLY single-line JSON.

Format: {"intent":"...","entities":{"loan_ids":[],"borrower_names":[],"amounts":[],"dates":[],"stages":[],"team_members":[]},"urgency":"...","complexity":"...","required_tools":[...],"requires_action":false}

Intents: pipeline_status, lead_management, team_performance, task_management, communication, document_analysis, market_intelligence, financial_analysis, predictive_analytics, action_request, general_query

Available tools: {tools}

Rules:
- leads/prospects -> lead_management, use ["lead_status_insights"]
- loans/pipeline/deals -> pipeline_status, use ["get_pipeline","get_pipeline_metrics"]
- tasks/priorities -> task_management, use ["get_daily_priorities","get_tasks"]
- rates/lock/float -> market_intelligence, use ["get_rate_lock_advisory","get_pipeline"]
- Default: task_management with ["get_daily_priorities","get_pipeline"]

Urgency: critical|high|medium|low. Return ONLY JSON."""


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

            # Use pattern-determined tools if specified (even if empty list)
            # Empty list [] means "no tools needed" which is different from None/missing
            final_tools = pattern_result["tools"] if pattern_result.get("tools") is not None else scoped_tools

            state_updates = {
                "query_intent": pattern_result["intent"],
                "query_entities": entities,
                "extracted_entities": pattern_result.get("extracted_entities", {}),
                "query_urgency": pattern_result["urgency"],
                "query_complexity": pattern_result["complexity"],
                "required_tools": final_tools,
                "requires_action": pattern_result.get("requires_action", False),
                "analysis_method": "pattern_match",
                "intent_agents": _resolve_consolidated_agents(intent_str),
                # Pass use_haiku flag for model selection in reason_and_respond
                "use_haiku": pattern_result.get("use_haiku", False),
                "intent_str": pattern_result.get("intent_str", intent_str),
            }

            # For greeting/simple intents with no tools, set data_quality early
            # so downstream nodes don't treat it as "unknown" if gather is skipped
            if not final_tools:
                state_updates["data_quality"] = "not_needed"

            state = update_state(state, state_updates)

            # =============================================================
            # MEMORY RETRIEVAL (skip for greetings/simple — saves ~20-50ms DB round-trip)
            # =============================================================
            _intent_str_val = pattern_result.get("intent_str", intent_str)
            _skip_memory = _intent_str_val in ("greeting", "simple")

            if not _skip_memory:
                mem_start = time.time()
                user_memories, memory_context = await _retrieve_user_memories(
                    state.get("user_id", ""), state.get("organization_id"),
                    current_query=state.get("user_message", "")
                )
                timing["memory_retrieve"] = (time.time() - mem_start) * 1000
                if user_memories or memory_context:
                    state = update_state(state, {
                        "user_memories": user_memories,
                        "memory_context": memory_context,
                    })
            else:
                timing["memory_retrieve"] = 0.0
                logger.debug(f"[ANALYZE] Skipping memory retrieval for '{_intent_str_val}' intent")

            node_time = (time.time() - node_start) * 1000
            use_haiku = pattern_result.get("use_haiku", False)
            logger.info(
                f"[ANALYZE] FAST PATH complete in {node_time:.1f}ms | "
                f"pattern_match={timing['pattern_match']:.1f}ms | "
                f"memory={timing.get('memory_retrieve', 0):.1f}ms | "
                f"intent={pattern_result['intent'].value}, use_haiku={use_haiku}, tools={final_tools}"
            )
            logger.info(f"[ANALYZE] ========== END (pattern_match) ==========")

            return state

        # =================================================================
        # STEP 2: Use intent router for classification (~1-5ms pattern, ~500-1000ms LLM)
        #         OPTIMIZATION: Skip if orchestrator already classified with high confidence
        # =================================================================
        pre_classified_intent = state.get("pre_classified_intent")
        pre_classified_confidence = state.get("intent_confidence", 0)

        if pre_classified_intent and pre_classified_confidence >= 0.90:
            # Orchestrator already classified this with high confidence — skip re-classification
            intent_str = pre_classified_intent
            confidence = pre_classified_confidence
            agents = state.get("intent_agents", ["pipeline_coach"])
            method = f"pre_classified ({state.get('pre_classified_method', 'unknown')})"
            timing["intent_classify"] = 0.0

            logger.info(
                f"[ANALYZE] ⚡ SKIP re-classification: pre_classified '{intent_str}' "
                f"(conf={confidence:.2f}, method={method})"
            )
        else:
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
            "historical": QueryIntent.FINANCIAL_ANALYSIS,  # Historical comparisons (Q3 vs Q4)
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
            "profit": QueryIntent.FINANCIAL_ANALYSIS,
            "operations": QueryIntent.PIPELINE_STATUS,
            "compound": QueryIntent.GENERAL_QUERY,
            "content_marketing": QueryIntent.COMMUNICATION,
            "top_leads": QueryIntent.LEAD_MANAGEMENT,
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
        # Check if this intent should use the fast Haiku model
        use_haiku = is_haiku_intent(intent_str)

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

        # =================================================================
        # MEMORY RETRIEVAL (after intent classification, before return)
        # =================================================================
        mem_start = time.time()
        user_memories, memory_context = await _retrieve_user_memories(
            state.get("user_id", ""), state.get("organization_id"),
            current_query=user_message,
        )
        timing["memory_retrieve"] = (time.time() - mem_start) * 1000
        if user_memories or memory_context:
            state = update_state(state, {
                "user_memories": user_memories,
                "memory_context": memory_context,
            })

        node_time = (time.time() - node_start) * 1000
        logger.info(
            f"[ANALYZE] ⏱️ TIMING BREAKDOWN:\n"
            f"  - pattern_match: {timing.get('pattern_match', 0):.1f}ms\n"
            f"  - intent_classify: {timing.get('intent_classify', 0):.1f}ms\n"
            f"  - tool_scope: {timing.get('tool_scope', 0):.1f}ms\n"
            f"  - entity_extract: {timing.get('entity_extract', 0):.1f}ms\n"
            f"  - memory_retrieve: {timing.get('memory_retrieve', 0):.1f}ms\n"
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
            "intent_agents": ["pipeline_coach"],
        })
