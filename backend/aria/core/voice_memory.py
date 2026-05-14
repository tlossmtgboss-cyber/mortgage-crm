"""
aria/core/voice_memory.py
Perennia AI — Voice-Specific Memory

Remembers voice interaction patterns and preferences per LO,
making Aria feel personal and context-aware across sessions.

Uses Redis for fast access with in-memory fallback.
Preferences are lightweight key-value pairs, not full conversation history.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("aria.voice_memory")

# In-memory fallback when Redis isn't available
_memory_fallback: Dict[str, Dict[str, Any]] = {}

# Keys for voice preferences
PREF_GREETING_STYLE = "greeting_style"       # formal, casual, first_name_only
PREF_BRIEFING_DEPTH = "briefing_depth"       # concise, standard, detailed
PREF_FAVORITE_METRICS = "favorite_metrics"   # list of metric names they always ask about
PREF_RESPONSE_LENGTH = "response_length"     # short, medium, long
PREF_VOICE_SPEED = "voice_speed"             # normal, fast, slow
PREF_PREFERRED_NAME = "preferred_name"       # what they want to be called


def _get_redis():
    """Get Redis client, returns None if unavailable."""
    try:
        from services.redis_service import redis_service
        return redis_service.get_client()
    except Exception:
        return None


class VoiceMemory:
    """Remembers voice interaction patterns and preferences per LO."""

    REDIS_PREFIX = "aria:voice_memory:"
    REDIS_TTL = 86400 * 90  # 90 days

    def __init__(self, organization_id: Optional[str] = None):
        self._org_id = organization_id

    def _key(self, user_id: str) -> str:
        return f"{self.REDIS_PREFIX}{user_id}"

    def _borrower_key(self, user_id: str, borrower_name: str) -> str:
        safe_name = borrower_name.lower().replace(" ", "_")[:50]
        return f"{self.REDIS_PREFIX}{user_id}:borrower:{safe_name}"

    # ─── Preference Storage ──────────────────────────────────────────

    def remember_preference(self, user_id: str, key: str, value: Any) -> None:
        """Store a voice preference for a user.

        Args:
            user_id: The LO's user ID.
            key: Preference key (use PREF_* constants).
            value: Preference value.
        """
        prefs = self._load_preferences(user_id)
        prefs[key] = value
        prefs["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._save_preferences(user_id, prefs)

    def get_preference(self, user_id: str, key: str, default: Any = None) -> Any:
        """Get a specific voice preference."""
        prefs = self._load_preferences(user_id)
        return prefs.get(key, default)

    def get_all_preferences(self, user_id: str) -> Dict[str, Any]:
        """Get all voice preferences for a user."""
        return self._load_preferences(user_id)

    # ─── Greeting & Style ────────────────────────────────────────────

    def get_greeting_style(self, user_id: str) -> str:
        """Get the preferred greeting style for this LO.

        Returns 'casual' (Hey Tim), 'formal' (Good morning Timothy),
        or 'first_name_only' (Tim, what can I help with?).
        Default: casual.
        """
        return self.get_preference(user_id, PREF_GREETING_STYLE, "casual")

    def get_preferred_name(self, user_id: str) -> Optional[str]:
        """Get what the LO prefers to be called."""
        return self.get_preference(user_id, PREF_PREFERRED_NAME)

    def build_greeting(self, user_id: str, user_name: str) -> str:
        """Build a personalized greeting based on preferences.

        Args:
            user_id: The LO's user ID.
            user_name: The LO's full name from the system.

        Returns:
            A greeting instruction for the LLM.
        """
        preferred_name = self.get_preferred_name(user_id) or user_name.split()[0]
        style = self.get_greeting_style(user_id)

        now = datetime.now(timezone.utc)
        hour = now.hour

        if style == "formal":
            time_greeting = "Good morning" if hour < 12 else "Good afternoon" if hour < 17 else "Good evening"
            return f"Greet them formally: '{time_greeting}, {preferred_name}. How can I help you today?'"
        elif style == "first_name_only":
            return f"Greet them briefly: '{preferred_name}, what do you need?'"
        else:  # casual (default)
            return f"Greet them casually: 'Hey {preferred_name}, what can I help you with?'"

    # ─── Briefing Preferences ────────────────────────────────────────

    def get_briefing_depth(self, user_id: str) -> str:
        """Get preferred briefing depth: concise, standard, or detailed."""
        return self.get_preference(user_id, PREF_BRIEFING_DEPTH, "standard")

    def get_favorite_metrics(self, user_id: str) -> List[str]:
        """Get the metrics this LO always asks about."""
        return self.get_preference(user_id, PREF_FAVORITE_METRICS, [])

    def record_metric_query(self, user_id: str, metric_name: str) -> None:
        """Track that the LO asked about a specific metric.

        After enough queries, this metric becomes a 'favorite'
        that Aria includes in briefings automatically.
        """
        counters = self.get_preference(user_id, "_metric_counters", {})
        counters[metric_name] = counters.get(metric_name, 0) + 1
        self.remember_preference(user_id, "_metric_counters", counters)

        # Promote to favorites if queried 3+ times
        favorites = self.get_favorite_metrics(user_id)
        if counters[metric_name] >= 3 and metric_name not in favorites:
            favorites.append(metric_name)
            self.remember_preference(user_id, PREF_FAVORITE_METRICS, favorites)

    # ─── Borrower Context Memory ─────────────────────────────────────

    def remember_borrower_context(
        self, user_id: str, borrower_name: str, context: str
    ) -> None:
        """Remember context about a borrower from voice interactions.

        Example: 'Last time you asked about the Johnsons, they were waiting on appraisal.'

        Args:
            user_id: The LO's user ID.
            borrower_name: The borrower's name.
            context: The context to remember.
        """
        key = self._borrower_key(user_id, borrower_name)
        data = self._load_raw(key) or {"interactions": []}

        data["interactions"].append({
            "context": context,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        # Keep last 10 interactions per borrower
        data["interactions"] = data["interactions"][-10:]
        data["last_mentioned"] = datetime.now(timezone.utc).isoformat()

        self._save_raw(key, data)

    def get_borrower_context(
        self, user_id: str, borrower_name: str
    ) -> Optional[str]:
        """Get the most recent voice context about a borrower.

        Returns a spoken summary like 'Last time you asked about the Johnsons,
        they were waiting on the appraisal.'
        """
        key = self._borrower_key(user_id, borrower_name)
        data = self._load_raw(key)
        if not data or not data.get("interactions"):
            return None

        last = data["interactions"][-1]
        return last.get("context", "")

    def get_all_borrower_contexts(
        self, user_id: str, borrower_name: str
    ) -> List[Dict[str, str]]:
        """Get all remembered contexts for a borrower."""
        key = self._borrower_key(user_id, borrower_name)
        data = self._load_raw(key)
        if not data:
            return []
        return data.get("interactions", [])

    # ─── Interaction Pattern Learning ────────────────────────────────

    def record_interaction_pattern(
        self, user_id: str, intent: str, time_of_day: str
    ) -> None:
        """Record when the LO uses Aria and for what.

        Used to learn patterns like 'always checks pipeline at 8am'
        or 'sends SMS campaigns on Fridays'.
        """
        patterns = self.get_preference(user_id, "_interaction_patterns", [])
        patterns.append({
            "intent": intent,
            "time_of_day": time_of_day,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        # Keep last 200 patterns
        patterns = patterns[-200:]
        self.remember_preference(user_id, "_interaction_patterns", patterns)

    # ─── Persistence Layer ───────────────────────────────────────────

    def _load_preferences(self, user_id: str) -> Dict[str, Any]:
        """Load all preferences for a user from Redis or memory."""
        return self._load_raw(self._key(user_id)) or {}

    def _save_preferences(self, user_id: str, prefs: Dict[str, Any]) -> None:
        """Save preferences to Redis or memory."""
        self._save_raw(self._key(user_id), prefs)

    def _load_raw(self, key: str) -> Optional[Dict[str, Any]]:
        """Load data from Redis or memory fallback."""
        redis = _get_redis()
        if redis:
            try:
                raw = redis.get(key)
                if raw:
                    return json.loads(raw)
            except Exception as e:
                logger.debug("Redis load failed for %s: %s", key, e)

        return _memory_fallback.get(key)

    def _save_raw(self, key: str, data: Dict[str, Any]) -> None:
        """Save data to Redis or memory fallback."""
        redis = _get_redis()
        if redis:
            try:
                redis.setex(key, self.REDIS_TTL, json.dumps(data, default=str))
                return
            except Exception as e:
                logger.debug("Redis save failed for %s: %s", key, e)

        _memory_fallback[key] = data
