"""
Response Caching Layer

Caches AI responses for common queries to:
1. Reduce AI API costs
2. Improve response time
3. Ensure consistency for similar questions

Smart caching based on:
- Query similarity
- Session context
- Response quality
"""

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
import redis

logger = logging.getLogger(__name__)


class ResponseCache:
    """
    Intelligent caching layer for AI responses.

    Caching strategy:
    - Educational content: Long TTL (7 days)
    - General questions: Medium TTL (24 hours)
    - Personalized responses: Not cached
    - CTA responses: Not cached
    """

    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self.DEFAULT_TTL = 3600 * 24  # 24 hours
        self.LONG_TTL = 3600 * 24 * 7  # 7 days

        # Queries that should be cached longer (educational)
        self.LONG_CACHE_PATTERNS = [
            'what is',
            'what are',
            'explain',
            'how does',
            'how do',
            'difference between',
            'what\'s the difference',
            'tell me about',
            'can you explain',
        ]

        # Patterns that should NOT be cached
        self.NO_CACHE_PATTERNS = [
            'my situation',
            'my budget',
            'my credit',
            'my timeline',
            'my property',
            'for me',
            'should i',
            'can i',
        ]

    def _get_cache_key(
        self,
        session_context: Dict[str, Any],
        user_message: str
    ) -> str:
        """Generate cache key based on context + message"""
        # Normalize message
        normalized_msg = user_message.lower().strip()
        normalized_msg = ' '.join(normalized_msg.split())  # Remove extra whitespace

        # Include relevant context that affects the response
        context_keys = {
            'phase': session_context.get('current_phase', 1),
            # Band intent score to increase cache hits (0-24, 25-49, 50-74, 75-100)
            'intent_band': (session_context.get('intent_score', 0) // 25) * 25,
            # Key signals that change response
            'has_property': 'property' in str(session_context.get('intent_signals', [])),
            'has_timeline': 'timeline' in str(session_context.get('intent_signals', [])),
            'lo_id': session_context.get('loan_officer_id'),
            # TENANT-004: Namespace cache by organization to prevent cross-tenant leakage
            'org_id': session_context.get('organization_id'),
        }

        cache_input = f"{json.dumps(context_keys, sort_keys=True)}:{normalized_msg}"
        return f"response_cache:{hashlib.sha256(cache_input.encode()).hexdigest()[:24]}"

    def should_cache(self, user_message: str, response: str) -> bool:
        """Determine if response should be cached"""
        msg_lower = user_message.lower()
        response_lower = response.lower()

        # Don't cache personalized responses
        for pattern in self.NO_CACHE_PATTERNS:
            if pattern in response_lower:
                return False

        # Don't cache CTA-containing responses
        if '{{CTA:' in response or 'call now' in response_lower:
            return False

        # Don't cache very short responses (probably errors or clarifications)
        if len(response) < 100:
            return False

        # Don't cache responses with specific numbers that might be personalized
        if '$' in response and any(c.isdigit() for c in response):
            # Exception: educational content about general ranges
            if 'typical' not in response_lower and 'generally' not in response_lower:
                return False

        # Cache educational content
        if any(pattern in msg_lower for pattern in self.LONG_CACHE_PATTERNS):
            return True

        # Cache substantial responses (>200 chars)
        return len(response) > 200

    async def get(
        self,
        session_context: Dict[str, Any],
        user_message: str
    ) -> Optional[str]:
        """Get cached response if available"""
        key = self._get_cache_key(session_context, user_message)

        try:
            cached = self.redis.get(key)

            if cached:
                # Track cache hit
                self.redis.incr("cache:hits")
                logger.debug(f"Cache hit: {key[:20]}...")
                return cached if isinstance(cached, str) else cached.decode('utf-8')

            # Track cache miss
            self.redis.incr("cache:misses")
            return None

        except redis.RedisError as e:
            logger.error(f"Redis error getting cached response: {e}")
            return None

    async def set(
        self,
        session_context: Dict[str, Any],
        user_message: str,
        response: str
    ):
        """Cache response if appropriate"""
        if not self.should_cache(user_message, response):
            return

        key = self._get_cache_key(session_context, user_message)

        # Determine TTL
        ttl = self.DEFAULT_TTL
        if any(p in user_message.lower() for p in self.LONG_CACHE_PATTERNS):
            ttl = self.LONG_TTL

        try:
            self.redis.setex(key, ttl, response)
            logger.debug(f"Cached response: {key[:20]}... TTL={ttl}")

        except redis.RedisError as e:
            logger.error(f"Redis error caching response: {e}")

    async def invalidate_for_session(self, session_id: str):
        """Invalidate all cached responses for a session (if context changes significantly)"""
        # This is a no-op in the current design since we don't key by session_id
        # But could be used if we add session-specific caching
        pass

    async def get_stats(self) -> Dict[str, Any]:
        """Get cache performance statistics"""
        try:
            hits = int(self.redis.get("cache:hits") or 0)
            misses = int(self.redis.get("cache:misses") or 0)
            total = hits + misses

            # Count cached entries
            cached_count = 0
            cursor = 0
            while True:
                cursor, keys = self.redis.scan(cursor, match="response_cache:*", count=100)
                cached_count += len(keys)
                if cursor == 0:
                    break

            return {
                'hits': hits,
                'misses': misses,
                'total_requests': total,
                'hit_rate': round(hits / total * 100, 2) if total > 0 else 0,
                'cached_responses': cached_count,
                'estimated_cost_savings': hits * 0.003,  # Approximate $ saved per cached response
            }

        except redis.RedisError as e:
            logger.error(f"Redis error getting cache stats: {e}")
            return {'error': str(e)}

    async def warm_cache(self, common_questions: List[Dict[str, str]]):
        """
        Pre-populate cache with responses to common questions.
        Call during startup or periodically.

        Args:
            common_questions: List of {"question": "...", "response": "...", "context": {...}}
        """
        for item in common_questions:
            await self.set(
                session_context=item.get('context', {'current_phase': 1}),
                user_message=item['question'],
                response=item['response']
            )
        logger.info(f"Warmed cache with {len(common_questions)} responses")


# Common questions for cache warming
COMMON_MORTGAGE_QUESTIONS = [
    {
        "question": "What is PMI?",
        "context": {"current_phase": 2},
        "response": """PMI (Private Mortgage Insurance) is insurance that protects the lender if you default on your loan. It's typically required when your down payment is less than 20% of the home's purchase price.

Here's what you should know about PMI:

**Cost**: Usually 0.5% to 1% of your loan amount annually, added to your monthly payment.

**When it goes away**: Once you reach 20% equity in your home (either through payments or appreciation), you can request to have PMI removed. By law, it must be automatically removed at 22% equity.

**Ways to avoid PMI**:
- Put 20% or more down
- Piggyback loans (80-10-10)
- Lender-paid PMI (slightly higher rate)
- VA loans (no PMI required)

Would you like me to explain any of these options in more detail?"""
    },
    {
        "question": "What's the difference between FHA and conventional loans?",
        "context": {"current_phase": 2},
        "response": """Great question! Here's a clear comparison of FHA vs Conventional loans:

**FHA Loans**:
- Minimum down payment: 3.5%
- Credit score: 580+ for 3.5% down, 500-579 for 10% down
- Mortgage insurance: Required for the life of the loan (unless you put 10%+ down)
- Debt-to-income: More flexible, up to 50% in some cases
- Best for: First-time buyers, lower credit scores, smaller down payments

**Conventional Loans**:
- Minimum down payment: 3% (with some programs)
- Credit score: Typically 620+, better rates at 740+
- PMI: Required under 20% down, but can be removed later
- Debt-to-income: Usually capped at 45%
- Best for: Good credit, larger down payments, avoiding long-term mortgage insurance

**The trade-off**: FHA is easier to qualify for, but you'll pay mortgage insurance longer. Conventional has stricter requirements but can save money long-term.

Which scenario sounds closer to your situation?"""
    },
    {
        "question": "How much do I need for a down payment?",
        "context": {"current_phase": 2},
        "response": """Down payment requirements vary quite a bit depending on your situation. Here's the breakdown:

**Minimum Down Payments by Loan Type**:
- **Conventional**: 3% (first-time buyers) to 5% (others)
- **FHA**: 3.5% (580+ credit) or 10% (500-579 credit)
- **VA**: 0% (for eligible veterans)
- **USDA**: 0% (rural areas, income limits apply)

**What to Consider**:

1. **Lower down payment** = Higher monthly payment + mortgage insurance
2. **20% down** = No PMI, lower monthly payment, but more cash upfront
3. **Sweet spot for many**: 10-15% balances cash on hand vs monthly payment

**Example**: On a $300,000 home:
- 3% down = $9,000
- 10% down = $30,000
- 20% down = $60,000

**Don't forget closing costs!** Budget an additional 2-5% of the purchase price.

What price range are you considering? I can help you think through the numbers."""
    },
]
