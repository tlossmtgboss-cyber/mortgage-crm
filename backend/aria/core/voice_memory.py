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
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("aria.voice_memory")


class _BoundedDict(OrderedDict):
    """LRU dict with max size to prevent memory leaks."""

    def __init__(self, max_size: int = 500):
        super().__init__()
        self._max_size = max_size

    def __setitem__(self, key, value):
        if key in self:
            self.move_to_end(key)
        super().__setitem__(key, value)
        while len(self) > self._max_size:
            self.popitem(last=False)


# In-memory fallback when Redis isn't available (bounded to prevent leaks)
_memory_fallback: Dict[str, Dict[str, Any]] = _BoundedDict(max_size=500)

# Lazy table creation flag
_table_checked = False


def _ensure_table() -> None:
    """Create voice_preferences table if it doesn't exist (idempotent)."""
    global _table_checked
    if _table_checked:
        return
    try:
        from db import engine
        from sqlalchemy import text
        with engine.begin() as conn:
            conn.execute(text(
                "CREATE TABLE IF NOT EXISTS voice_preferences ("
                "cache_key VARCHAR(255) PRIMARY KEY, "
                "preferences JSONB NOT NULL DEFAULT '{}', "
                "updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW())"
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_voice_prefs_updated "
                "ON voice_preferences (updated_at)"
            ))
        _table_checked = True
    except Exception as e:
        logger.debug("voice_preferences table check failed: %s", e)
        _table_checked = True  # Don't retry on failure


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
        if self._org_id:
            return f"{self.REDIS_PREFIX}{self._org_id}:{user_id}"
        return f"{self.REDIS_PREFIX}{user_id}"

    def _borrower_key(self, user_id: str, borrower_name: str) -> str:
        safe_name = borrower_name.lower().replace(" ", "_")[:50]
        if self._org_id:
            return f"{self.REDIS_PREFIX}{self._org_id}:{user_id}:borrower:{safe_name}"
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

    def _pg_save(self, key: str, data: Dict[str, Any]) -> None:
        """Write-through to PostgreSQL for durability."""
        try:
            _ensure_table()
            from db import SessionLocal
            db = SessionLocal()
            try:
                from sqlalchemy import text
                db.execute(text(
                    "INSERT INTO voice_preferences (cache_key, preferences, updated_at) "
                    "VALUES (:key, :data, NOW()) "
                    "ON CONFLICT (cache_key) DO UPDATE SET preferences = :data, updated_at = NOW()"
                ), {"key": key, "data": json.dumps(data, default=str)})
                db.commit()
            except Exception as e:
                logger.debug("PG write-through failed for %s: %s", key, e)
                db.rollback()
            finally:
                db.close()
        except Exception as e:
            logger.debug("PG write-through unavailable: %s", e)

    def _pg_load(self, key: str) -> Optional[Dict[str, Any]]:
        """Load from PostgreSQL fallback."""
        try:
            _ensure_table()
            from db import SessionLocal
            db = SessionLocal()
            try:
                from sqlalchemy import text
                row = db.execute(text(
                    "SELECT preferences FROM voice_preferences WHERE cache_key = :key"
                ), {"key": key}).fetchone()
                if row and row[0]:
                    return json.loads(row[0]) if isinstance(row[0], str) else row[0]
            except Exception as e:
                logger.debug("PG load failed for %s: %s", key, e)
            finally:
                db.close()
        except Exception:
            pass
        return None

    def _load_raw(self, key: str) -> Optional[Dict[str, Any]]:
        """Load data from Redis, PostgreSQL backup, or memory fallback."""
        # Try Redis first
        redis = _get_redis()
        if redis:
            try:
                raw = redis.get(key)
                if raw:
                    return json.loads(raw)
            except Exception as e:
                logger.debug("Redis load failed for %s: %s", key, e)

        # Try PostgreSQL backup
        pg_data = self._pg_load(key)
        if pg_data is not None:
            # Warm Redis cache back up
            if redis:
                try:
                    redis.setex(key, self.REDIS_TTL, json.dumps(pg_data, default=str))
                except Exception:
                    pass
            return pg_data

        # In-memory fallback (last resort)
        return _memory_fallback.get(key)

    def _save_raw(self, key: str, data: Dict[str, Any]) -> None:
        """Save data to Redis (primary), PostgreSQL (durable backup), and memory (fallback)."""
        redis = _get_redis()
        if redis:
            try:
                redis.setex(key, self.REDIS_TTL, json.dumps(data, default=str))
            except Exception as e:
                logger.debug("Redis save failed for %s: %s", key, e)

        # PostgreSQL write-through for durability (after Redis)
        self._pg_save(key, data)

        # Always update in-memory fallback
        _memory_fallback[key] = data
