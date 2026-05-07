"""
Intent Router - Fast Intent Classification & Agent Routing

This module provides ultra-fast intent classification (<100ms) to route queries
to the appropriate specialized agents, loading only 8-16 tools instead of 160.

Performance improvement:
- Before: All 160 tools loaded on every request
- After: Only 8-16 relevant tools loaded based on intent

Caching:
- LLM-based classification is cached in Redis with 24h TTL
- Same query string returns cached intent (avoids redundant API calls)
- Pattern matching remains instant (~1-5ms) with no caching needed

Usage:
    from agents.intent_router import classify_intent, get_tools_for_intent

    # Fast classification (<100ms with pattern matching, <1s with LLM)
    intent = await classify_intent("How is my lead pipeline?")
    # Returns: "leads"

    # Get relevant agent tools
    tools = get_tools_for_intent(intent, db, current_user)
    # Returns: Dict with only lead_nurturer tools (8 tools)
"""

import os
import re
import time
import logging
import threading
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

# Import LLM cache service for caching intent classification
try:
    from services.llm_cache_service import llm_cache, LLMCacheService
    LLM_CACHE_AVAILABLE = True
except ImportError:
    llm_cache = None
    LLMCacheService = None
    LLM_CACHE_AVAILABLE = False

logger = logging.getLogger(__name__)

# Cache version — increment on any change to intent mappings, patterns, or LLM prompt.
# This prefix is added to all cache keys so stale entries from previous deployments
# are automatically bypassed without waiting for TTL expiration.
INTENT_CACHE_VERSION = "v7"


# =============================================================================
# INTENT DEFINITIONS
# =============================================================================

class Intent(str, Enum):
    """Query intent categories mapped to specialized agents."""
    GREETING = "greeting"          # Simple greetings (hi, hello, etc.) - use Haiku
    SIMPLE = "simple"              # Simple lookups, basic info - use Haiku
    PIPELINE = "pipeline"          # Loan pipeline analytics
    HISTORICAL = "historical"      # Historical comparisons (Q3 vs Q4, period performance)
    COMPLIANCE = "compliance"      # Regulatory compliance
    TASKS = "tasks"                # Task management
    PRIORITIES = "priorities"      # Daily priorities (combines pipeline + tasks)
    LEADS = "leads"                # Lead management and nurturing
    DOCUMENTS = "documents"        # Document tracking
    RATES = "rates"                # Rate lock advisory
    SCHEDULE = "schedule"          # Appointment scheduling
    SLA = "sla"                    # SLA tracking
    CALLS = "calls"                # Phone calls
    EMAIL = "email"                # Email management
    VIDEO = "video"                # Video meetings
    REPORTS = "reports"            # Reporting
    BILLING = "billing"            # Subscription/billing
    COACHING = "coaching"          # Team performance coaching
    CUSTOMER = "customer"          # Customer intelligence
    INTEGRATIONS = "integrations"  # LOS/vendor integrations
    COMPOUND = "compound"          # Multi-action commands (e.g., "text X and schedule Y")
    PROFIT = "profit"              # Profitability, margins, revenue analysis
    NOTIFICATIONS = "notifications"  # Notification management, alert preferences
    ONBOARDING = "onboarding"      # Setup, guided tours, training, checklists
    GENERAL = "general"            # Default fallback


# =============================================================================
# INTENTS THAT USE HAIKU (Fast, simple responses)
# =============================================================================

HAIKU_INTENTS = {
    "greeting",          # Greetings - no data needed
    "simple",            # Simple lookups, yes/no, thanks
    "schedule",          # Calendar scheduling - tools do the work
    "coaching",          # Team coaching - database-driven metrics
    "video",             # Video meeting management - tool-based
    "calls",             # Phone call management - tool-based routing
    "sla",               # SLA tracking - deadline/metric lookup
    "documents",         # Document tracking - checklist/status lookup
    "notifications",     # Notification management - tool-based CRUD
    "onboarding",        # Onboarding steps/checklists - deterministic
    "content_marketing", # Content marketing queries - tool-based
    "customer",          # Customer 360 - database-driven lookups
    "tasks",             # Task management - deterministic tool output
}

# Intents that require Sonnet for complex reasoning/analysis
SONNET_INTENTS = {
    "pipeline",          # Pipeline analytics require nuanced analysis
    "leads",             # Lead management needs contextual recommendations
    "compliance",        # Regulatory compliance needs precise reasoning
    "compound",          # Multi-action commands need careful orchestration
    "rates",             # Rate advisory needs analytical reasoning for lock/float decisions
    "historical",        # Historical comparisons need analytical depth
    "priorities",        # Daily priorities combine multiple data sources
    "profit",            # Profitability analysis needs financial reasoning
    "reports",           # Complex analytical reasoning, anomaly detection, narrative generation
    "billing",           # Consultative retention reasoning, cancellation handling
    "integrations",      # Complex diagnostic reasoning, conflict resolution, migration planning
}


def is_haiku_intent(intent: str) -> bool:
    """Check if an intent should use the fast Haiku model.

    Returns True for intents where tools do the heavy lifting and the LLM
    only needs to format/summarize the result. Returns False for intents
    requiring complex reasoning, analysis, or multi-step orchestration.
    """
    # Explicit Sonnet intents always use Sonnet
    if intent in SONNET_INTENTS:
        return False
    # Explicit Haiku intents use Haiku
    if intent in HAIKU_INTENTS:
        return True
    # Default: use Sonnet for unknown intents (safer)
    return False


# =============================================================================
# INTENT TO AGENTS MAPPING
# =============================================================================

INTENT_TO_AGENTS: Dict[str, List[str]] = {
    # Core intents (original 21 agents)
    "greeting": [],                                       # No tools needed - direct Haiku response
    "simple": ["pipeline_analyst"],                       # Basic lookup with Haiku
    "pipeline": ["pipeline_analyst", "revenue_forecaster"],
    "historical": ["pipeline_analyst"],                   # Historical comparisons (Q3 vs Q4, etc.)
    "compliance": ["compliance_checker", "quality_control"],
    "tasks": ["task_automation"],
    "priorities": ["pipeline_analyst", "task_automation"],
    "top_leads": ["lead_nurturer"],                       # Specific for "call my top leads" queries
    "leads": ["lead_nurturer", "pre_approval_specialist"],
    "documents": ["document_tracker", "closing_coordinator"],
    "rates": ["rate_advisor", "secondary_market"],
    "schedule": ["smart_scheduler"],
    "sla": ["sla_tracker"],
    "calls": ["voice_os", "ai_receptionist"],
    "email": ["email_intelligence"],
    "video": ["uvip"],
    "reports": ["reporting_engine"],
    "billing": ["subscription_manager"],
    "coaching": ["team_coach", "training_specialist"],
    "customer": ["customer_intelligence", "borrower_concierge"],
    "integrations": ["integrations", "migration_assistant"],
    "operations": ["ops_manager"],
    "profit": ["profitability_analyst", "pricing_strategist"],
    "notifications": ["notification_center"],
    "onboarding": ["onboarding_assistant"],

    # Revenue & Production intents
    "revenue": ["revenue_forecaster", "profitability_analyst"],
    "pricing": ["pricing_strategist", "rate_advisor"],
    "closing": ["closing_coordinator", "document_tracker"],
    "structuring": ["loan_structuring", "pricing_strategist"],

    # Borrower Experience intents
    "borrower": ["borrower_concierge", "pre_approval_specialist"],
    "pre_approval": ["pre_approval_specialist"],
    "credit_repair": ["credit_repair_advisor"],
    "down_payment": ["down_payment_advisor"],
    "post_closing": ["post_closing_care", "review_manager"],

    # Risk & Fraud intents
    "fraud": ["fraud_detector"],
    "risk": ["risk_assessor", "quality_control"],
    "qc": ["quality_control", "compliance_checker"],
    "turn_down": ["turn_down_specialist"],

    # Marketing & Content intents
    "content": ["content_creator", "social_media_manager"],
    "social_media": ["social_media_manager"],
    "market": ["market_analyst"],
    "campaign": ["campaign_manager"],
    "reviews": ["review_manager"],

    # HR & Workforce intents
    "recruiting": ["recruiter"],
    "training": ["training_specialist"],
    "performance": ["performance_manager", "team_coach"],

    # Partner & Referral intents
    "referral": ["referral_partner_manager"],
    "title": ["title_vendor_manager"],
    "appraisal": ["appraiser_coordinator"],
    "insurance": ["insurance_coordinator"],

    # Operations intents
    "warehouse": ["warehouse_manager"],
    "shipping": ["shipping_coordinator"],
    "secondary": ["secondary_market", "rate_advisor"],
    "servicing": ["servicing_transfer"],
    "investor": ["investor_relations"],

    # Platform intents
    "system_health": ["system_health_monitor"],
    "data_quality": ["data_quality_manager"],
    "migration": ["migration_assistant"],

    # Specialty Lending intents
    "va_loan": ["va_loan_specialist"],
    "fha_loan": ["fha_loan_specialist"],
    "jumbo": ["jumbo_specialist"],
    "reverse_mortgage": ["reverse_mortgage_advisor"],
    "construction": ["construction_loan_advisor"],
    "commercial": ["commercial_bridge"],

    # Compound & fallback
    "compound": ["pipeline_analyst", "lead_nurturer", "smart_scheduler", "email_intelligence", "voice_os", "task_automation", "closing_coordinator"],
    "general": ["pipeline_analyst", "task_automation"],  # Default
}


# =============================================================================
# FAST PATTERN MATCHING
# =============================================================================

# Regex patterns for ultra-fast intent classification (~1-5ms)
INTENT_PATTERNS: Dict[str, List[str]] = {
    # Greetings - use Haiku for fast response
    "greeting": [
        r"^(hi|hey|hello|howdy|yo|sup|morning|afternoon|evening)\b",
        r"^(good\s*)?(morning|afternoon|evening)",
        r"^what'?s? up\b",
        r"^how are you",
        r"^how'?s? it going",
    ],
    # Simple queries - use Haiku
    "simple": [
        r"^(thanks?|thank you)",
        r"^(ok|okay|got it|sounds good|perfect)",
        r"^(yes|no|yep|nope|sure|maybe)",
        r"what (can|do) you do",
        r"help me",
        r"^(bye|goodbye|see you|later)",
    ],
    # Compound intents - MUST come before individual intents to catch multi-action commands
    # e.g., "send a text and schedule a meeting" would also match "email" for "send"
    "compound": [
        r"(send|text|message|sms|email).{1,40}(and|then|also|plus).{1,40}(schedule|book|set up|arrange|calendar)",
        r"(schedule|book|set up|arrange).{1,40}(and|then|also|plus).{1,40}(send|text|message|sms|email)",
        r"(text|message|sms).{1,40}(and|then).{1,40}(schedule|book|set up|arrange|call|meet)",
        r"(call|contact|reach out).{1,40}(and|then).{1,40}(schedule|book|set up|calendar)",
    ],
    # Historical comparisons - MUST come before pipeline to match Q3/Q4 queries
    "historical": [
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
    "priorities": [
        r"(top|my|daily|today'?s?) ?(priorit|urgent|important)",
        r"what (should|do) i (do|focus|work)",
        r"(start|begin) (my|the) day",
        r"morning brief",
        r"what'?s? (on my|my) (plate|agenda)",
    ],
    "tasks": [
        r"\btasks?\b",
        r"to.?do",
        r"overdue",
        r"due (today|tomorrow|this week)",
        r"reminders?",
        r"follow.?up",
        # Call list queries
        r"what (calls?|people) (do i |should i |to )?(need to )?(make|call|contact)",
        r"who (do i |should i )?need to (call|contact|reach out)",
        r"call (list|queue)",
        r"calls? (i need|to make)",
    ],
    # Top leads - specific high-priority pattern for "call my top leads" type queries
    # Must come BEFORE "leads" to match first
    "top_leads": [
        r"(get|show|give|list) (me )?(my |the )?(top|best|highest|hot|priority) ?\d* ?(leads?|prospects?)",
        r"(my |the )?(top|best|highest|hot) ?\d* ?(leads?|prospects?) (to call|for calling|with phone)",
        r"call (my |the )?(top|best|hot|warm|priority|highest)( \d+)? (leads?|prospects?)",
        r"(top|best|hot|priority) \d+ (leads?|contacts?|prospects?)",
        r"who (should|do|can) i call (first|next|today)",
    ],
    "leads": [
        r"\bleads?\b",
        r"prospects?",
        r"lead (pipeline|funnel|conversion|bottleneck)",
        r"nurture",
        r"who (should|to) (call|contact)",
        r"speed to lead",
        r"lead (score|scoring|analytics)",
        # General lead calling without specific "top" keyword
        r"(call|contact|reach out to) (my )?leads",
        # Contact frequency patterns - leads not contacted recently
        r"(leads?|prospects?) (not |haven't been |i haven't )?contacted",
        r"(haven't|have not|not) contacted",
        r"(stale|inactive|cold|dormant) (leads?|prospects?)",
        r"last contact(ed)?",
        r"(not )?(contacted|reached) in \d+ (days?|weeks?)",
        r"overdue (for )?contact",
    ],
    "pipeline": [
        r"(loan|loans) (pipeline|funnel)",
        r"(my|the) pipeline",
        r"(closing|funded|processing|underwriting)",
        r"(deals?|applications?) (in|at|stuck)",
        r"pipeline (summary|status|metrics)",
    ],
    "rates": [
        r"\brates?\b",
        r"lock (or|vs|versus) float",
        r"should (i|we) lock",
        r"rate (lock|advisory|recommendation)",
        r"(current|today'?s?) (rate|pricing)",
        r"float",
    ],
    "calls": [
        r"\b(call|dial|phone|ring)\b",
        r"click.?to.?dial",
        r"make a call",
        r"(outbound|inbound) call",
        r"voicemail",
        r"transcri(be|ption)",
    ],
    "email": [
        # Action-based email patterns (highest priority - user wants to DO something with email)
        r"(send|draft|compose|write|forward|reply) (an? )?(email|message|note) to",
        r"(send|draft|compose|write) .{1,50} (an? )?(email|message)",
        r"(email|message|write to|send to) [A-Z][a-z]+ [A-Z][a-z]+",  # email John Smith
        r"(send|email) (it|this|that) to",
        # General email patterns
        r"\bemail\b",
        r"email (template|thread)",
        r"inbox",
        r"(need|have) to respond",
        r"respond to",
        r"unread",
        r"(urgent|priority) (email|message)",
        r"search (my )?(email|inbox|mail)",
        r"find (email|message|correspondence)",
        r"(referral|partner)",  # Referral partners often involves email lookup
        r"reschedule",  # Often involves sending email
    ],
    "schedule": [
        r"\bschedul(e|ing)\b",
        r"\bappointment",
        r"\bmeeting\b",
        r"(book|cancel|reschedule)",
        r"calendar",
        r"availab(le|ility)",
    ],
    "documents": [
        r"\bdocument",
        r"condition",
        r"missing (doc|document|file)",
        r"(upload|submit|request) (doc|document)",
        r"third.?party",
        r"appraisal|title|insurance",
    ],
    "compliance": [
        r"complian(ce|t)",
        r"\bTRID\b",
        r"\bRESPA\b",
        r"fair lending",
        r"disclosure",
        r"regulat(ory|ion)",
        r"audit",
    ],
    "sla": [
        r"\bSLA\b",
        r"service level",
        r"breach",
        r"(stage|status) (time|duration)",
        r"aging",
    ],
    "video": [
        r"video (meeting|call|conference)",
        r"zoom|teams|webex",
        r"screen.?share",
        r"record(ing)?",
    ],
    "reports": [
        r"\breport\b",
        r"export",
        r"dashboard",
        r"analytics",
        r"metrics",
        r"production (report|numbers)",
        r"\btrend",
        r"\bkpi\b",
        r"business intelligence",
    ],
    "billing": [
        r"subscript",
        r"billing",
        r"payment",
        r"invoice",
        r"plan|pricing|upgrade",
    ],
    "coaching": [
        r"coach(ing)?",
        r"performance",
        r"training",
        r"improvement",
        r"best practice",
        r"(team|lo) (metrics|stats)",
    ],
    "customer": [
        r"customer",
        r"360.?view",
        r"relationship",
        r"lifetime value|ltv",
        r"churn",
        r"referral",
    ],
    "integrations": [
        r"integrat",
        r"\bLOS\b",
        r"credit (pull|report)",
        r"\bAUS\b",
        r"e.?sign",
        r"sync",
    ],
    "operations": [
        r"(ops|operations?) (manager|sweep|scan|check)",
        r"pipeline (sweep|scan|health|check)",
        r"(impediment|blocker|stuck|stalled)",
        r"(team|staff) (gap|assignment|missing)",
        r"(unassigned|missing) (lo|loan officer|processor|closer)",
        r"run (a )?sweep",
    ],
    "profit": [
        r"\bprofit\w*\b",
        r"\bmargin[s]?\b",
        r"\brevenue\b",
        r"\bcost.per.loan\b",
        r"\bpricing\s+optim",
    ],
    "notifications": [
        r"\bnotif",
        r"alert (settings?|preferences?|config)",
        r"quiet hours?",
        r"notification (preferences?|settings?|center)",
        r"send (an? )?alert",
        r"(mute|unmute|silence) (notifications?|alerts?)",
        r"(push|email|sms) (notifications?|alerts?)",
    ],
    "onboarding": [
        r"\bonboard",
        r"\bsetup (wizard|guide|process)\b",
        r"getting started",
        r"first time",
        r"guided tour",
        r"\btraining (resource|module|video|guide)",
        r"(onboarding|setup) checklist",
        r"new user (setup|guide)",
    ],
}


# =============================================================================
# ROUTING STATS & PATTERN LEARNING
# =============================================================================

class _RoutingStats:
    """Thread-safe in-memory routing statistics with periodic DB persistence."""

    _PERSIST_INTERVAL = 300  # Persist every 5 minutes
    _FALLBACK_WARN_THRESHOLD = 0.50  # Warn when fallback rate > 50%

    def __init__(self):
        self._lock = threading.Lock()
        self.total_requests: int = 0
        self.regex_hits: int = 0
        self.llm_fallbacks: int = 0
        self.learned_hits: int = 0
        self._last_persist_time: float = time.time()
        self._warned_high_fallback: bool = False

    def record_regex_hit(self) -> None:
        with self._lock:
            self.total_requests += 1
            self.regex_hits += 1
            self._maybe_persist()

    def record_llm_fallback(self) -> None:
        with self._lock:
            self.total_requests += 1
            self.llm_fallbacks += 1
            self._check_fallback_rate()
            self._maybe_persist()

    def record_learned_hit(self) -> None:
        with self._lock:
            self.total_requests += 1
            self.learned_hits += 1
            self._maybe_persist()

    def get_stats(self) -> dict:
        with self._lock:
            total = max(self.total_requests, 1)
            return {
                "total_requests": self.total_requests,
                "regex_hits": self.regex_hits,
                "llm_fallbacks": self.llm_fallbacks,
                "learned_hits": self.learned_hits,
                "regex_hit_rate": round(self.regex_hits / total, 4),
                "llm_fallback_rate": round(self.llm_fallbacks / total, 4),
                "learned_hit_rate": round(self.learned_hits / total, 4),
            }

    def _check_fallback_rate(self) -> None:
        """Warn once when fallback rate exceeds threshold."""
        if self.total_requests < 20:
            return  # Not enough data
        rate = self.llm_fallbacks / self.total_requests
        if rate > self._FALLBACK_WARN_THRESHOLD and not self._warned_high_fallback:
            self._warned_high_fallback = True
            logger.warning(
                f"[INTENT] High LLM fallback rate: {rate:.0%} "
                f"({self.llm_fallbacks}/{self.total_requests}). "
                f"Consider adding regex patterns for common queries."
            )
        elif rate <= self._FALLBACK_WARN_THRESHOLD:
            self._warned_high_fallback = False

    def _maybe_persist(self) -> None:
        """Fire-and-forget DB persist if interval elapsed."""
        now = time.time()
        if now - self._last_persist_time < self._PERSIST_INTERVAL:
            return
        self._last_persist_time = now
        stats = {
            "total_requests": self.total_requests,
            "regex_hits": self.regex_hits,
            "llm_fallbacks": self.llm_fallbacks,
            "learned_hits": self.learned_hits,
        }
        thread = threading.Thread(
            target=_persist_routing_stats, args=(stats,), daemon=True
        )
        thread.start()


# Singleton stats tracker
_routing_stats = _RoutingStats()


def _persist_routing_stats(stats: dict) -> None:
    """Persist routing stats snapshot to DB (runs in background thread)."""
    try:
        from db import SessionLocal
        from database.models.learning_example import LearningPattern

        db = SessionLocal()
        try:
            pattern = db.query(LearningPattern).filter(
                LearningPattern.pattern_type == "routing_stats",
                LearningPattern.pattern_key == "cumulative",
            ).first()

            if pattern:
                pattern.extra_metadata = stats
                pattern.last_seen_at = datetime.now(timezone.utc)
                pattern.occurrence_count = stats["total_requests"]
            else:
                pattern = LearningPattern(
                    pattern_type="routing_stats",
                    pattern_key="cumulative",
                    pattern_value="intent_router_stats",
                    confidence=1.0,
                    occurrence_count=stats["total_requests"],
                    extra_metadata=stats,
                    last_seen_at=datetime.now(timezone.utc),
                    is_active=True,
                )
                db.add(pattern)
            db.commit()
        except Exception as e:
            logger.debug(f"[INTENT] Stats persist failed: {e}")
            db.rollback()
        finally:
            db.close()
    except Exception as e:
        logger.debug(f"[INTENT] Stats persist setup failed: {e}")


# In-memory buffer of LLM fallback mappings: query_normalized -> {intent, count}
_llm_mapping_buffer: Dict[str, Dict[str, Any]] = defaultdict(
    lambda: {"intent": None, "count": 0, "queries": []}
)
_llm_buffer_lock = threading.Lock()

# Minimum times an LLM classification must be seen before suggesting a pattern
PATTERN_LEARNING_THRESHOLD = 5

# Runtime learned patterns merged from DB (loaded at startup or via apply)
_learned_patterns: Dict[str, List[str]] = {}
_learned_patterns_lock = threading.Lock()


def _normalize_for_learning(query: str) -> str:
    """Normalize query for pattern learning — lowercase, strip, collapse whitespace."""
    return re.sub(r"\s+", " ", query.lower().strip())


def _record_llm_classification(query: str, intent: str) -> None:
    """
    Record an LLM fallback classification for pattern learning.
    When the same intent is seen PATTERN_LEARNING_THRESHOLD times,
    persist a LearningPattern record in a background thread.
    """
    normalized = _normalize_for_learning(query)

    should_persist = False
    with _llm_buffer_lock:
        entry = _llm_mapping_buffer[normalized]
        if entry["intent"] == intent:
            entry["count"] += 1
        else:
            # New or changed intent — reset counter
            entry["intent"] = intent
            entry["count"] = 1
            entry["queries"] = []
        if len(entry["queries"]) < 10:
            entry["queries"].append(query)

        if entry["count"] >= PATTERN_LEARNING_THRESHOLD:
            should_persist = True
            # Reset so we don't persist repeatedly
            persist_data = {
                "intent": entry["intent"],
                "count": entry["count"],
                "queries": list(entry["queries"]),
            }
            entry["count"] = 0

    if should_persist:
        thread = threading.Thread(
            target=_persist_learned_pattern,
            args=(normalized, persist_data),
            daemon=True,
        )
        thread.start()


def _persist_learned_pattern(normalized_query: str, data: dict) -> None:
    """Persist a learned intent mapping to the DB (background thread)."""
    try:
        from db import SessionLocal
        from database.models.learning_example import LearningPattern

        intent = data["intent"]
        # Build a regex-safe escaped pattern from the normalized query
        suggested_regex = re.escape(normalized_query)

        db = SessionLocal()
        try:
            existing = db.query(LearningPattern).filter(
                LearningPattern.pattern_type == "intent_mapping",
                LearningPattern.pattern_key == f"{intent}:{normalized_query}",
            ).first()

            if existing:
                existing.occurrence_count += data["count"]
                existing.last_seen_at = datetime.now(timezone.utc)
                existing.confidence = min(
                    1.0, float(existing.occurrence_count) / (PATTERN_LEARNING_THRESHOLD * 4)
                )
                existing.extra_metadata = {
                    **(existing.extra_metadata or {}),
                    "sample_queries": data["queries"][:10],
                }
            else:
                new_pattern = LearningPattern(
                    pattern_type="intent_mapping",
                    pattern_key=f"{intent}:{normalized_query}",
                    pattern_value=suggested_regex,
                    confidence=round(
                        data["count"] / (PATTERN_LEARNING_THRESHOLD * 4), 4
                    ),
                    occurrence_count=data["count"],
                    last_seen_at=datetime.now(timezone.utc),
                    extra_metadata={
                        "intent": intent,
                        "sample_queries": data["queries"][:10],
                        "auto_learned": True,
                    },
                    is_active=False,  # Inactive until explicitly applied
                )
                db.add(new_pattern)

            db.commit()
            logger.info(
                f"[INTENT] Learned pattern: '{normalized_query}' -> {intent} "
                f"(count={data['count']})"
            )
        except Exception as e:
            logger.debug(f"[INTENT] Pattern persist failed: {e}")
            db.rollback()
        finally:
            db.close()
    except Exception as e:
        logger.debug(f"[INTENT] Pattern persist setup failed: {e}")


def load_learned_patterns() -> int:
    """
    Load active learned patterns from the DB and merge into runtime patterns.
    Call at startup to augment hardcoded INTENT_PATTERNS.

    Returns number of patterns loaded.
    """
    loaded = 0
    try:
        from db import SessionLocal
        from database.models.learning_example import LearningPattern

        db = SessionLocal()
        try:
            active_patterns = db.query(LearningPattern).filter(
                LearningPattern.pattern_type == "intent_mapping",
                LearningPattern.is_active == True,
            ).all()

            new_patterns: Dict[str, List[str]] = defaultdict(list)
            for p in active_patterns:
                # pattern_key format: "intent:normalized_query"
                intent = (p.extra_metadata or {}).get("intent")
                if not intent:
                    parts = p.pattern_key.split(":", 1)
                    intent = parts[0] if parts else None
                if intent and intent in INTENT_TO_AGENTS and p.pattern_value:
                    new_patterns[intent].append(p.pattern_value)
                    loaded += 1

            with _learned_patterns_lock:
                _learned_patterns.clear()
                _learned_patterns.update(new_patterns)

            if loaded > 0:
                logger.info(f"[INTENT] Loaded {loaded} learned patterns from DB")
        except Exception as e:
            logger.debug(f"[INTENT] Failed to load learned patterns: {e}")
        finally:
            db.close()
    except Exception as e:
        logger.debug(f"[INTENT] Learned patterns load setup failed: {e}")

    return loaded


def get_routing_stats() -> dict:
    """Return current routing hit/fallback rates."""
    return _routing_stats.get_stats()


def get_learned_patterns() -> list:
    """
    Return all discovered patterns from LLM fallbacks.
    Includes both active (applied) and inactive (pending review) patterns.
    """
    results = []
    try:
        from db import SessionLocal
        from database.models.learning_example import LearningPattern

        db = SessionLocal()
        try:
            patterns = db.query(LearningPattern).filter(
                LearningPattern.pattern_type == "intent_mapping",
            ).order_by(LearningPattern.occurrence_count.desc()).limit(100).all()

            for p in patterns:
                meta = p.extra_metadata or {}
                intent = meta.get("intent", p.pattern_key.split(":")[0])
                results.append({
                    "id": p.id,
                    "intent": intent,
                    "pattern": p.pattern_value,
                    "occurrence_count": p.occurrence_count,
                    "confidence": float(p.confidence) if p.confidence else 0.0,
                    "is_active": p.is_active,
                    "sample_queries": meta.get("sample_queries", []),
                    "last_seen_at": str(p.last_seen_at) if p.last_seen_at else None,
                })
        except Exception as e:
            logger.error(f"[INTENT] Failed to fetch learned patterns: {e}")
        finally:
            db.close()
    except Exception as e:
        logger.debug(f"[INTENT] Learned patterns fetch setup failed: {e}")

    return results


def apply_learned_patterns(min_confidence: float = 0.25, min_occurrences: int = 10) -> int:
    """
    Activate high-confidence learned patterns and merge into runtime regex.

    Args:
        min_confidence: Minimum confidence to auto-activate (0-1)
        min_occurrences: Minimum occurrence count to auto-activate

    Returns number of patterns activated.
    """
    activated = 0
    try:
        from db import SessionLocal
        from database.models.learning_example import LearningPattern

        db = SessionLocal()
        try:
            candidates = db.query(LearningPattern).filter(
                LearningPattern.pattern_type == "intent_mapping",
                LearningPattern.is_active == False,
                LearningPattern.confidence >= min_confidence,
                LearningPattern.occurrence_count >= min_occurrences,
            ).all()

            new_patterns: Dict[str, List[str]] = defaultdict(list)
            for p in candidates:
                meta = p.extra_metadata or {}
                intent = meta.get("intent", p.pattern_key.split(":")[0])
                if intent in INTENT_TO_AGENTS and p.pattern_value:
                    p.is_active = True
                    p.updated_at = datetime.now(timezone.utc)
                    new_patterns[intent].append(p.pattern_value)
                    activated += 1

            if activated > 0:
                db.commit()
                with _learned_patterns_lock:
                    for intent, patterns in new_patterns.items():
                        if intent not in _learned_patterns:
                            _learned_patterns[intent] = []
                        _learned_patterns[intent].extend(patterns)
                logger.info(
                    f"[INTENT] Activated {activated} learned patterns "
                    f"(min_conf={min_confidence}, min_occ={min_occurrences})"
                )
        except Exception as e:
            logger.error(f"[INTENT] Failed to apply learned patterns: {e}")
            db.rollback()
        finally:
            db.close()
    except Exception as e:
        logger.debug(f"[INTENT] Apply patterns setup failed: {e}")

    return activated


# =============================================================================
# FAST PATTERN MATCHING
# =============================================================================

def classify_intent_fast(query: str) -> Tuple[Optional[str], float, Optional[str]]:
    """
    Ultra-fast intent classification using regex patterns.

    Checks hardcoded INTENT_PATTERNS first, then runtime learned patterns.

    Returns:
        Tuple of (intent, confidence, matched_pattern)
        Returns (None, 0, None) if no pattern matches
    """
    query_lower = query.lower().strip()

    # 1. Try hardcoded patterns (highest confidence)
    for intent, patterns in INTENT_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, query_lower, re.IGNORECASE):
                logger.debug(f"[INTENT] Fast match: '{pattern}' -> {intent}")
                return (intent, 1.0, pattern)

    # 2. Try learned patterns (slightly lower confidence)
    with _learned_patterns_lock:
        for intent, patterns in _learned_patterns.items():
            for pattern in patterns:
                try:
                    if re.search(pattern, query_lower, re.IGNORECASE):
                        logger.debug(f"[INTENT] Learned match: '{pattern}' -> {intent}")
                        return (intent, 0.90, f"learned:{pattern}")
                except re.error:
                    # Bad regex from learned pattern — skip
                    logger.debug(f"[INTENT] Invalid learned regex: {pattern}")
                    continue

    return (None, 0.0, None)


# =============================================================================
# LLM-BASED INTENT CLASSIFICATION (Fallback)
# =============================================================================

INTENT_CLASSIFIER_PROMPT = """Classify this mortgage CRM query into ONE category. Return ONLY the category name.

Categories:
- priorities: Daily priorities, what to focus on, morning briefing
- tasks: Task management, to-dos, follow-ups
- leads: Lead pipeline, prospects, nurturing, who to call
- pipeline: Loan pipeline, deals, closing, processing status
- historical: Quarter/month comparisons (Q3 vs Q4), period performance, historical data
- rates: Interest rates, lock/float decisions
- calls: Phone calls, click-to-dial, voicemail
- email: Email management, drafting, templates
- schedule: Appointments, meetings, calendar
- documents: Document tracking, conditions, uploads
- compliance: TRID, RESPA, fair lending, disclosures
- sla: SLA tracking, stage timing, breaches
- video: Video meetings, recordings
- reports: Reports, dashboards, analytics exports
- billing: Subscription, billing, payments
- coaching: Team performance, training, metrics
- customer: Customer 360, relationships, referrals
- integrations: LOS sync, credit pulls, AUS
- profit: Profitability analysis, margins, revenue, cost per loan, pricing optimization
- notifications: Notification management, alert preferences, quiet hours, delivery status
- onboarding: Setup wizard, getting started, guided tour, training resources, checklists
- compound: Multiple actions in one request (e.g., "text John and schedule a call")
- general: Unclear or single ambiguous category

Query: {query}

Category:"""


async def classify_intent_llm(
    query: str,
    anthropic_client = None
) -> Tuple[str, float]:
    """
    LLM-based intent classification for complex/ambiguous queries.

    This is slower (~500-1000ms) but handles edge cases better.
    Only called when pattern matching fails.

    Caching:
    - Results are cached in Redis with 24h TTL
    - Same query returns cached intent (saves ~$0.01 per call)
    - Cache key is based on query hash

    Returns:
        Tuple of (intent, confidence)
    """
    start = time.time()

    # Check cache first (if available)
    # Cache key includes INTENT_CACHE_VERSION so deployments with changed
    # intent mappings automatically bypass stale entries
    cache_key = None
    if LLM_CACHE_AVAILABLE and llm_cache and llm_cache._enabled:
        cache_key = llm_cache._generate_key(f"intent_{INTENT_CACHE_VERSION}", query.lower().strip())
        cached = llm_cache.get(cache_key)
        if cached:
            elapsed = (time.time() - start) * 1000
            logger.info(f"[INTENT] Cache HIT: '{cached.get('intent')}' in {elapsed:.1f}ms")
            return (cached.get("intent", "general"), cached.get("confidence", 0.85))

    if anthropic_client is None:
        from .anthropic_client import get_anthropic_client
        anthropic_client = get_anthropic_client()

    try:
        # Use prompt caching: static classification instructions as cached system prompt,
        # only the user query varies per call
        response = anthropic_client.messages.create(
            model=os.getenv("ANTHROPIC_FAST_MODEL", "claude-haiku-4-5-20251001"),  # Fastest model for classification
            max_tokens=10,  # Intent is a single word — 10 tokens is plenty
            system=[
                {
                    "type": "text",
                    "text": INTENT_CLASSIFIER_PROMPT.split("Query:")[0].strip(),
                    "cache_control": {"type": "ephemeral"}
                }
            ],
            messages=[{
                "role": "user",
                "content": f"Query: {query}\n\nCategory:"
            }],
            timeout=5.0,  # Intent classification should complete in <1s
        )

        intent = response.content[0].text.strip().lower()
        elapsed = (time.time() - start) * 1000

        logger.info(f"[INTENT] LLM classification: '{intent}' in {elapsed:.0f}ms")

        # Validate intent — assign confidence based on response quality
        if intent in INTENT_TO_AGENTS:
            # Higher confidence if the response was clean (single word, exact match)
            if intent in [v.value for v in Intent]:
                llm_confidence = 0.85
            else:
                llm_confidence = 0.75  # Known agent mapping but not canonical intent
            result = (intent, llm_confidence)
        else:
            logger.warning(f"[INTENT] Unknown intent from LLM: {intent}")
            result = ("general", 0.5)

        # Cache the result (24 hour TTL - intents are stable)
        if LLM_CACHE_AVAILABLE and llm_cache and llm_cache._enabled and cache_key:
            llm_cache.set(cache_key, {"intent": result[0], "confidence": result[1]}, ttl=86400)
            logger.debug(f"[INTENT] Cached intent '{result[0]}' for 24h")

        return result

    except Exception as e:
        # Distinguish API errors from other failures for observability
        err_name = type(e).__name__
        if "AuthenticationError" in err_name:
            logger.critical(f"[INTENT] Anthropic API authentication failed: {e}")
        elif "RateLimitError" in err_name:
            logger.warning(f"[INTENT] Anthropic API rate limit hit: {e}")
        else:
            logger.error(f"[INTENT] LLM classification failed ({err_name}): {e}", exc_info=True)
        return ("general", 0.3)


# =============================================================================
# MAIN CLASSIFICATION FUNCTION
# =============================================================================

async def classify_intent(
    query: str,
    anthropic_client = None,
    use_llm_fallback: bool = True
) -> Dict[str, Any]:
    """
    Classify query intent using fast pattern matching, with LLM fallback.

    Performance:
    - Pattern match: ~1-5ms (handles 80%+ of queries)
    - LLM fallback: ~500-1000ms (for complex/ambiguous queries)

    Args:
        query: User's input query
        anthropic_client: Optional pre-configured Anthropic client
        use_llm_fallback: Whether to use LLM for unmatched queries

    Returns:
        Dict with:
        - intent: The classified intent
        - confidence: Confidence score (0-1)
        - agents: List of agent names to use
        - method: 'pattern_match' or 'llm'
        - elapsed_ms: Classification time in milliseconds
    """
    start = time.time()

    # Guard against None/empty/non-string input
    if not query or not isinstance(query, str):
        return {
            "intent": "general",
            "confidence": 0.0,
            "agents": INTENT_TO_AGENTS["general"],
            "method": "fallback",
            "matched_pattern": None,
            "elapsed_ms": 0.0,
        }
    # Truncate long inputs to prevent regex DoS on adversarial strings
    query = query[:1000]

    # Try fast pattern matching first (hardcoded + learned patterns)
    intent, confidence, pattern = classify_intent_fast(query)

    if intent:
        elapsed = (time.time() - start) * 1000

        # Track whether this was a hardcoded or learned pattern hit
        if pattern and pattern.startswith("learned:"):
            _routing_stats.record_learned_hit()
            method = "learned_pattern"
        else:
            _routing_stats.record_regex_hit()
            method = "pattern_match"

        logger.info(
            f"[INTENT] {method}: {intent} (conf={confidence:.2f}) in {elapsed:.1f}ms"
        )
        return {
            "intent": intent,
            "confidence": confidence,
            "agents": INTENT_TO_AGENTS.get(intent, INTENT_TO_AGENTS["general"]),
            "method": method,
            "matched_pattern": pattern,
            "elapsed_ms": elapsed
        }

    # Fall back to LLM if enabled
    if use_llm_fallback:
        _routing_stats.record_llm_fallback()
        intent, confidence = await classify_intent_llm(query, anthropic_client)
        elapsed = (time.time() - start) * 1000

        # Record this LLM classification for pattern learning (fire-and-forget)
        if intent and intent != "general":
            _record_llm_classification(query, intent)

        # Log low-confidence routes for review
        if confidence < 0.7:
            logger.warning(
                f"[INTENT] Low-confidence LLM route: '{query[:80]}' -> {intent} "
                f"(conf={confidence:.2f})"
            )

        return {
            "intent": intent,
            "confidence": confidence,
            "agents": INTENT_TO_AGENTS.get(intent, INTENT_TO_AGENTS["general"]),
            "method": "llm",
            "matched_pattern": None,
            "elapsed_ms": elapsed
        }

    # Default fallback
    elapsed = (time.time() - start) * 1000
    return {
        "intent": "general",
        "confidence": 0.3,
        "agents": INTENT_TO_AGENTS["general"],
        "method": "fallback",
        "matched_pattern": None,
        "elapsed_ms": elapsed
    }


# =============================================================================
# TOOL LOADING BY INTENT
# =============================================================================

def get_agent_tools(agent_name: str) -> List[str]:
    """Get list of tool names for a specific agent."""
    from .tool_integration import AGENT_CONFIGS

    config = AGENT_CONFIGS.get(agent_name)
    if config:
        return config.tool_names
    return []


def get_tools_for_intent(intent: str) -> Dict[str, List[str]]:
    """
    Get all tools for the agents mapped to an intent.

    Returns:
        Dict mapping agent names to their tool lists
    """
    agents = INTENT_TO_AGENTS.get(intent, INTENT_TO_AGENTS["general"])

    result = {}
    for agent_name in agents:
        tools = get_agent_tools(agent_name)
        if tools:
            result[agent_name] = tools

    return result


def get_tool_count_for_intent(intent: str) -> int:
    """Get total number of tools that would be loaded for an intent."""
    tools_by_agent = get_tools_for_intent(intent)
    return sum(len(tools) for tools in tools_by_agent.values())


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def print_intent_summary():
    """Print summary of intents and their mapped agents/tools."""
    print("=" * 70)
    print("INTENT ROUTING SUMMARY")
    print("=" * 70)

    for intent, agents in INTENT_TO_AGENTS.items():
        tools_by_agent = get_tools_for_intent(intent)
        total_tools = sum(len(tools) for tools in tools_by_agent.values())

        print(f"\n{intent.upper()}")
        print(f"  Agents: {', '.join(agents)}")
        print(f"  Total tools: {total_tools}")
        for agent, tools in tools_by_agent.items():
            print(f"    {agent}: {len(tools)} tools")

    print("\n" + "=" * 70)


def flush_intent_cache() -> bool:
    """
    Flush all cached intent classifications.
    Call this after deployments that change intent mappings or patterns.
    Returns True if cache was flushed, False if cache unavailable.
    """
    if LLM_CACHE_AVAILABLE and llm_cache and llm_cache._enabled:
        try:
            # Incrementing INTENT_CACHE_VERSION in code is the primary mechanism.
            # This function provides a runtime fallback for hot-fixing.
            llm_cache.clear_prefix(f"intent_{INTENT_CACHE_VERSION}")
            logger.info(f"[INTENT] Cache flushed for version {INTENT_CACHE_VERSION}")
            return True
        except Exception as e:
            logger.error(f"[INTENT] Failed to flush cache: {e}")
            return False
    return False


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    "Intent",
    "INTENT_TO_AGENTS",
    "INTENT_CACHE_VERSION",
    "HAIKU_INTENTS",
    "SONNET_INTENTS",
    "is_haiku_intent",
    "classify_intent",
    "classify_intent_fast",
    "classify_intent_llm",
    "get_tools_for_intent",
    "get_agent_tools",
    "get_tool_count_for_intent",
    "flush_intent_cache",
    "print_intent_summary",
    # Pattern learning & stats
    "get_routing_stats",
    "get_learned_patterns",
    "apply_learned_patterns",
    "load_learned_patterns",
    "PATTERN_LEARNING_THRESHOLD",
]
