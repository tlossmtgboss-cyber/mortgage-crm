"""
aria/core/session_store.py
Perennia AI — Aria Session Store

Redis-backed session persistence for Aria conversations.
Stores conversation state (messages, slots, intent, phase) with a 24-hour TTL.
Falls back to in-memory storage if Redis is unavailable.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from langchain_core.messages import AIMessage, HumanMessage

logger = logging.getLogger(__name__)

# In-memory fallback
_memory_store: Dict[str, Dict] = {}

SESSION_TTL = 86400  # 24 hours


def _get_redis():
    """Get Redis client, returns None if unavailable."""
    try:
        from services.redis_service import redis_service
        return redis_service.get_client()
    except Exception:
        return None


def _serialize_messages(messages: list) -> list:
    """Serialize LangChain messages to JSON-safe dicts."""
    result = []
    for m in messages:
        if isinstance(m, HumanMessage):
            result.append({"role": "human", "content": m.content})
        elif isinstance(m, AIMessage):
            result.append({"role": "ai", "content": m.content})
    return result


def _deserialize_messages(data: list) -> list:
    """Deserialize JSON dicts back to LangChain messages."""
    result = []
    for m in data:
        if m["role"] == "human":
            result.append(HumanMessage(content=m["content"]))
        elif m["role"] == "ai":
            result.append(AIMessage(content=m["content"]))
    return result


class AriaSessionStore:

    async def get_or_create(
        self, session_id: str,
        user_id: str, org_id: str,
        user_name: str, user_role: str,
        user_email: str = "",
    ) -> Dict[str, Any]:
        """Load existing session or create a new one."""
        existing = await self._load(session_id)
        if existing:
            return existing

        return {
            "messages": [],
            "intent": None,
            "slots": {},
            "missing_slots": [],
            "current_slot_question": None,
            "phase": "understanding",
            "task_result": None,
            "confirmation_preview": None,
            "user_id": user_id,
            "org_id": org_id,
            "user_name": user_name,
            "user_email": user_email,
            "user_role": user_role,
            "voice_preferences": None,  # Set by caller from VoiceMemory; not persisted
            "iteration_count": 0,
            "error": None,
        }

    async def save(self, session_id: str, state: Dict[str, Any]) -> None:
        """Persist session state."""
        serializable = {
            "messages": _serialize_messages(state.get("messages", [])),
            "intent": state.get("intent"),
            "slots": state.get("slots", {}),
            "missing_slots": state.get("missing_slots", []),
            "current_slot_question": state.get("current_slot_question"),
            "phase": str(state.get("phase", "")),
            "task_result": state.get("task_result"),
            "confirmation_preview": state.get("confirmation_preview"),
            "user_id": state.get("user_id", ""),
            "org_id": state.get("org_id", ""),
            "user_name": state.get("user_name", ""),
            "user_email": state.get("user_email", ""),
            "user_role": state.get("user_role", ""),
            "iteration_count": state.get("iteration_count", 0),
            "error": state.get("error"),
            "saved_at": datetime.now(timezone.utc).isoformat(),
        }

        redis = _get_redis()
        key = f"aria:session:{session_id}"

        if redis:
            try:
                redis.setex(key, SESSION_TTL, json.dumps(serializable))
                return
            except Exception as e:
                logger.warning(f"Redis save failed, using memory: {e}")

        _memory_store[session_id] = serializable

    async def _load(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Load session from Redis or memory."""
        redis = _get_redis()
        key = f"aria:session:{session_id}"

        data = None
        if redis:
            try:
                raw = redis.get(key)
                if raw:
                    data = json.loads(raw)
            except Exception as e:
                logger.warning(f"Redis load failed: {e}")

        if not data:
            data = _memory_store.get(session_id)

        if not data:
            return None

        # Deserialize messages back to LangChain objects
        data["messages"] = _deserialize_messages(data.get("messages", []))
        return data
