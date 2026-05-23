"""
Agent Memory Service

Provides high-level operations for persisting and retrieving AI agent
memories across conversation sessions.  The service is intentionally
opt-in: callers decide whether to invoke it.

Public API:
    save_conversation_summary(db, user_id, org_id, agent_role, messages, summary)
    get_relevant_context(db, user_id, org_id, agent_role, query, limit)
    save_memory(db, user_id, org_id, key, value, memory_type, agent_role, confidence, ttl)
    get_user_preferences(db, user_id, org_id)
    update_context(db, user_id, org_id, context_key, context_value)
    get_context(db, user_id, org_id, context_key)
    prune_expired_memories(db)
    get_conversation_history(db, user_id, org_id, agent_role, limit)

All functions accept an explicit SQLAlchemy ``Session`` so they integrate
cleanly with FastAPI's ``Depends(get_db)`` pattern.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lazy model imports (avoids circular imports at module load time)
# ---------------------------------------------------------------------------

_models_loaded = False
_AgentConversation = None
_AgentMemory = None
_AgentContext = None
_MemoryType = None


def _ensure_models():
    """Load models on first use."""
    global _models_loaded, _AgentConversation, _AgentMemory, _AgentContext, _MemoryType
    if _models_loaded:
        return
    from database.models.agent_memory import (
        AgentConversation,
        AgentMemory,
        AgentContext,
        MemoryType,
    )
    _AgentConversation = AgentConversation
    _AgentMemory = AgentMemory
    _AgentContext = AgentContext
    _MemoryType = MemoryType
    _models_loaded = True


# ---------------------------------------------------------------------------
# Roles that have memory enabled (opt-in list)
# ---------------------------------------------------------------------------

MEMORY_ENABLED_ROLES = {
    "pipeline_analyst",
    "compliance_checker",
    "lead_nurturer",
    "document_tracker",
    "team_coach",
    "rate_advisor",
    "receptionist",
    "customer_service",
    "scheduler",
}


def is_memory_enabled(agent_role: str) -> bool:
    """Check whether a given agent role has memory persistence enabled."""
    return agent_role in MEMORY_ENABLED_ROLES


# ============================================================================
# Conversation summaries
# ============================================================================

def save_conversation_summary(
    db: Session,
    user_id: int,
    org_id: Optional[int],
    agent_role: str,
    messages: Optional[List[Dict[str, Any]]] = None,
    summary: str = "",
    key_points: Optional[List[str]] = None,
) -> Optional[int]:
    """
    Persist a conversation summary after an agent session ends.

    Args:
        db: Active SQLAlchemy session.
        user_id: The user who participated.
        org_id: Tenant organization ID.
        agent_role: Which agent role handled the conversation.
        messages: Raw message list (used to derive message_count).
        summary: AI-generated summary text.
        key_points: Optional structured key points.

    Returns:
        The ID of the created AgentConversation row, or None on error.
    """
    _ensure_models()

    if not is_memory_enabled(agent_role):
        logger.debug("Memory not enabled for role %s, skipping save", agent_role)
        return None

    try:
        conversation = _AgentConversation(
            user_id=user_id,
            organization_id=org_id,
            agent_role=agent_role,
            started_at=datetime.now(timezone.utc),
            ended_at=datetime.now(timezone.utc),
            summary=summary,
            key_points=key_points,
            message_count=len(messages) if messages else 0,
        )
        db.add(conversation)
        db.flush()  # Get the ID without committing
        logger.info(
            "Saved conversation summary id=%s for user=%s role=%s",
            conversation.id, user_id, agent_role,
        )
        return conversation.id
    except Exception as e:
        logger.exception("Failed to save conversation summary: %s", e)
        return None


def get_conversation_history(
    db: Session,
    user_id: int,
    org_id: Optional[int] = None,
    agent_role: Optional[str] = None,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """
    Retrieve recent conversation summaries for a user.

    Returns a list of dicts with id, agent_role, summary, key_points,
    started_at, ended_at, message_count.
    """
    _ensure_models()
    try:
        query = db.query(_AgentConversation).filter(
            _AgentConversation.user_id == user_id,
        )
        if org_id is not None:
            query = query.filter(_AgentConversation.organization_id == org_id)
        if agent_role:
            query = query.filter(_AgentConversation.agent_role == agent_role)

        conversations = (
            query
            .order_by(_AgentConversation.started_at.desc())
            .limit(limit)
            .all()
        )

        return [
            {
                "id": c.id,
                "agent_role": c.agent_role,
                "summary": c.summary,
                "key_points": c.key_points,
                "started_at": c.started_at.isoformat() if c.started_at else None,
                "ended_at": c.ended_at.isoformat() if c.ended_at else None,
                "message_count": c.message_count,
            }
            for c in conversations
        ]
    except Exception as e:
        logger.exception("Failed to get conversation history: %s", e)
        return []


# ============================================================================
# Memory CRUD
# ============================================================================

def save_memory(
    db: Session,
    user_id: int,
    org_id: Optional[int],
    key: str,
    value: str,
    memory_type: str = "fact",
    agent_role: Optional[str] = None,
    confidence: float = 1.0,
    ttl: Optional[int] = None,
    conversation_id: Optional[int] = None,
) -> Optional[int]:
    """
    Store a single memory.

    If a memory with the same (user_id, org_id, key, memory_type) already
    exists, it is updated rather than duplicated.

    Args:
        ttl: Time-to-live in seconds.  If provided, sets expires_at.

    Returns:
        The memory row ID, or None on error.
    """
    _ensure_models()
    try:
        # Resolve enum value
        mem_type = _MemoryType(memory_type)

        # Check for existing memory with same key for this user
        existing = db.query(_AgentMemory).filter(
            _AgentMemory.user_id == user_id,
            _AgentMemory.key == key,
            _AgentMemory.memory_type == mem_type,
            _AgentMemory.organization_id == org_id if org_id else _AgentMemory.organization_id.is_(None),
        ).first()

        expires_at = None
        if ttl is not None:
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)

        # Best-effort embedding generation so memories are vector-searchable
        embedding = None
        emb_model = None
        try:
            from services.aria_memory.embedding_service import (
                generate_embedding_sync,
                EMBEDDING_MODEL,
            )
            embedding = generate_embedding_sync(value)
            if embedding is not None:
                emb_model = EMBEDDING_MODEL
        except Exception as e:
            logger.warning("Embedding generation failed for memory key=%s: %s", key, e)

        if existing:
            existing.value = value
            existing.confidence = confidence
            existing.agent_role = agent_role or existing.agent_role
            existing.expires_at = expires_at
            existing.conversation_id = conversation_id or existing.conversation_id
            if embedding is not None:
                existing.embedding = embedding
                existing.embedding_model = emb_model
            db.flush()
            logger.debug("Updated memory id=%s key=%s", existing.id, key)
            return existing.id
        else:
            memory = _AgentMemory(
                user_id=user_id,
                organization_id=org_id,
                conversation_id=conversation_id,
                memory_type=mem_type,
                key=key,
                value=value,
                confidence=confidence,
                agent_role=agent_role,
                expires_at=expires_at,
                embedding=embedding,
                embedding_model=emb_model,
            )
            db.add(memory)
            db.flush()
            logger.debug("Created memory id=%s key=%s", memory.id, key)
            return memory.id
    except Exception as e:
        logger.exception("Failed to save memory key=%s: %s", key, e)
        return None


def get_relevant_context(
    db: Session,
    user_id: int,
    org_id: Optional[int] = None,
    agent_role: Optional[str] = None,
    query: Optional[str] = None,
    limit: int = 20,
) -> Dict[str, Any]:
    """
    Retrieve relevant memories and recent conversation summaries for an
    agent session.

    The result is a dict with:
        - memories: list of matching AgentMemory dicts
        - recent_conversations: list of recent conversation summaries
        - context: dict of AgentContext key-value pairs

    If ``query`` is provided, memories whose key or value contain the query
    string (case-insensitive) are boosted.  All non-expired memories for the
    user are considered.
    """
    _ensure_models()
    result: Dict[str, Any] = {
        "memories": [],
        "recent_conversations": [],
        "context": {},
    }

    try:
        now = datetime.now(timezone.utc)

        # 1. Fetch non-expired memories for this user
        mem_query = db.query(_AgentMemory).filter(
            _AgentMemory.user_id == user_id,
            or_(
                _AgentMemory.expires_at.is_(None),
                _AgentMemory.expires_at > now,
            ),
            _AgentMemory.superseded_by.is_(None),
        )
        if org_id is not None:
            mem_query = mem_query.filter(_AgentMemory.organization_id == org_id)

        # Order by confidence desc, then most recent
        memories = (
            mem_query
            .order_by(_AgentMemory.confidence.desc(), _AgentMemory.created_at.desc())
            .limit(limit * 2)  # Fetch extra so we can filter/reorder
            .all()
        )

        # If a query string is provided, score memories by relevance
        scored = []
        for m in memories:
            relevance = m.confidence or 0.5
            if query:
                q_lower = query.lower()
                if q_lower in (m.key or "").lower():
                    relevance += 0.3
                if q_lower in (m.value or "").lower():
                    relevance += 0.2
            scored.append((relevance, m))

        scored.sort(key=lambda x: x[0], reverse=True)
        top_memories = scored[:limit]

        result["memories"] = [
            {
                "id": m.id,
                "key": m.key,
                "value": m.value,
                "memory_type": m.memory_type.value if m.memory_type else "fact",
                "confidence": m.confidence,
                "agent_role": m.agent_role,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for _, m in top_memories
        ]

        # 2. Recent conversations (last 5)
        conv_query = db.query(_AgentConversation).filter(
            _AgentConversation.user_id == user_id,
        )
        if org_id is not None:
            conv_query = conv_query.filter(_AgentConversation.organization_id == org_id)
        if agent_role:
            conv_query = conv_query.filter(_AgentConversation.agent_role == agent_role)

        recent_convs = (
            conv_query
            .order_by(_AgentConversation.started_at.desc())
            .limit(5)
            .all()
        )
        result["recent_conversations"] = [
            {
                "id": c.id,
                "agent_role": c.agent_role,
                "summary": c.summary,
                "key_points": c.key_points,
                "started_at": c.started_at.isoformat() if c.started_at else None,
            }
            for c in recent_convs
        ]

        # 3. Context key-value pairs
        ctx_query = db.query(_AgentContext).filter(
            _AgentContext.user_id == user_id,
        )
        if org_id is not None:
            ctx_query = ctx_query.filter(_AgentContext.organization_id == org_id)

        contexts = ctx_query.all()
        result["context"] = {
            c.context_key: c.context_value for c in contexts
        }

    except Exception as e:
        logger.exception("Failed to get relevant context: %s", e)

    return result


def get_user_preferences(
    db: Session,
    user_id: int,
    org_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Return all preference-type memories for a user.

    Returns list of dicts with key, value, confidence, agent_role.
    """
    _ensure_models()
    try:
        now = datetime.now(timezone.utc)
        query = db.query(_AgentMemory).filter(
            _AgentMemory.user_id == user_id,
            _AgentMemory.memory_type == _MemoryType.PREFERENCE,
            or_(
                _AgentMemory.expires_at.is_(None),
                _AgentMemory.expires_at > now,
            ),
            _AgentMemory.superseded_by.is_(None),
        )
        if org_id is not None:
            query = query.filter(_AgentMemory.organization_id == org_id)

        prefs = query.order_by(_AgentMemory.key).all()

        return [
            {
                "key": p.key,
                "value": p.value,
                "confidence": p.confidence,
                "agent_role": p.agent_role,
                "updated_at": p.updated_at.isoformat() if p.updated_at else None,
            }
            for p in prefs
        ]
    except Exception as e:
        logger.exception("Failed to get user preferences: %s", e)
        return []


# ============================================================================
# Context key-value operations
# ============================================================================

def update_context(
    db: Session,
    user_id: int,
    org_id: Optional[int],
    context_key: str,
    context_value: str,
) -> bool:
    """
    Set a context key-value pair (upsert semantics).

    Returns True on success.
    """
    _ensure_models()
    try:
        existing = db.query(_AgentContext).filter(
            _AgentContext.user_id == user_id,
            _AgentContext.context_key == context_key,
            _AgentContext.organization_id == org_id if org_id else _AgentContext.organization_id.is_(None),
        ).first()

        if existing:
            existing.context_value = context_value
        else:
            ctx = _AgentContext(
                user_id=user_id,
                organization_id=org_id,
                context_key=context_key,
                context_value=context_value,
            )
            db.add(ctx)

        db.flush()
        return True
    except Exception as e:
        logger.exception("Failed to update context key=%s: %s", context_key, e)
        return False


def get_context(
    db: Session,
    user_id: int,
    org_id: Optional[int] = None,
    context_key: Optional[str] = None,
) -> Dict[str, str]:
    """
    Get context values.  If context_key is provided, returns a single-entry
    dict.  Otherwise returns all context pairs for the user.
    """
    _ensure_models()
    try:
        query = db.query(_AgentContext).filter(
            _AgentContext.user_id == user_id,
        )
        if org_id is not None:
            query = query.filter(_AgentContext.organization_id == org_id)
        if context_key:
            query = query.filter(_AgentContext.context_key == context_key)

        rows = query.all()
        return {r.context_key: r.context_value for r in rows}
    except Exception as e:
        logger.exception("Failed to get context: %s", e)
        return {}


# ============================================================================
# Maintenance / cleanup
# ============================================================================

def prune_expired_memories(db: Session) -> int:
    """
    Delete all memories whose expires_at has passed.

    Returns the number of rows deleted.
    """
    _ensure_models()
    try:
        now = datetime.now(timezone.utc)
        count = (
            db.query(_AgentMemory)
            .filter(
                _AgentMemory.expires_at.isnot(None),
                _AgentMemory.expires_at <= now,
            )
            .delete(synchronize_session="fetch")
        )
        db.flush()
        if count:
            logger.info("Pruned %d expired agent memories", count)
        return count
    except Exception as e:
        logger.exception("Failed to prune expired memories: %s", e)
        return 0


def prune_old_conversations(
    db: Session,
    days: int = 180,
) -> int:
    """
    Delete conversation summaries older than ``days`` days.
    Associated memories are cascade-deleted.

    Returns the number of rows deleted.
    """
    _ensure_models()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        count = (
            db.query(_AgentConversation)
            .filter(_AgentConversation.started_at < cutoff)
            .delete(synchronize_session="fetch")
        )
        db.flush()
        if count:
            logger.info("Pruned %d old agent conversations (older than %d days)", count, days)
        return count
    except Exception as e:
        logger.exception("Failed to prune old conversations: %s", e)
        return 0
