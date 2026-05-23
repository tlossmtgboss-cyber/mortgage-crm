"""
Memory Conflict Detection & Resolution

Detects semantically contradictory memories for the same borrower
(e.g., "prefers morning calls" AND "prefers evening calls") and either
auto-resolves or flags for admin review.

Also provides confidence decay for memories that haven't been
verified recently.

Called after a new AgentMemory is committed — from staging approval
or auto-commit.
"""

import enum
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import List, Literal, Optional

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger("aria.conflict_detector")


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class SuggestedAction(str, enum.Enum):
    SUPERSEDE = "supersede"
    FLAG_FOR_REVIEW = "flag_for_review"
    KEEP_BOTH = "keep_both"


class ConflictResult(BaseModel):
    """A single conflict between the new memory and an existing one."""
    conflicting_memory_id: int
    conflicting_memory_value: str
    similarity_score: float
    match_type: Literal["fact_key", "embedding", "topic_type"]
    suggested_action: SuggestedAction


# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

# Embedding similarity above this = potential conflict
SIMILARITY_CONFLICT_THRESHOLD = 0.85

# Above this + same topic = auto-supersede (high confidence match)
SIMILARITY_AUTO_SUPERSEDE_THRESHOLD = 0.92

# Confidence decay settings
DECAY_90_DAY_MULTIPLIER = 0.9
DECAY_180_DAY_MULTIPLIER = 0.7


# ---------------------------------------------------------------------------
# Conflict Detection
# ---------------------------------------------------------------------------

def detect_conflicts(
    db: Session,
    memory: "AgentMemory",
) -> List[ConflictResult]:
    """
    Find existing memories that may conflict with a newly committed memory.

    Scoped to same borrower_id + organization_id for performance.
    Uses:
      1. fact_key match (exact key collision)
      2. pgvector cosine similarity (semantic similarity > 0.85)

    Only checks PREFERENCE and DIRECTIVE types — FACT and CONTEXT/INSIGHT
    can coexist even when similar.

    Returns list of ConflictResult sorted by similarity descending.
    """
    from database.models.agent_memory import AgentMemory, MemoryType

    start_ms = time.monotonic()
    conflicts: List[ConflictResult] = []

    # Only detect conflicts for preference/directive types
    conflictable_types = {MemoryType.PREFERENCE, MemoryType.DIRECTIVE}
    if memory.memory_type not in conflictable_types:
        return conflicts

    borrower_id = memory.borrower_id
    org_id = memory.organization_id

    if borrower_id is None or org_id is None:
        return conflicts

    # --- Pass 1: fact_key collision (if fact_key is set) ---
    if memory.fact_key:
        fact_key_matches = (
            db.query(AgentMemory)
            .filter(
                AgentMemory.id != memory.id,
                AgentMemory.borrower_id == borrower_id,
                AgentMemory.organization_id == org_id,
                AgentMemory.fact_key == memory.fact_key,
                AgentMemory.superseded_by.is_(None),
                AgentMemory.memory_type.in_([t.value for t in conflictable_types]),
            )
            .all()
        )
        for existing in fact_key_matches:
            conflicts.append(ConflictResult(
                conflicting_memory_id=existing.id,
                conflicting_memory_value=existing.value or "",
                similarity_score=1.0,  # Exact key match = maximum similarity
                match_type="fact_key",
                suggested_action=SuggestedAction.SUPERSEDE,
            ))

    # Collect IDs already found to avoid duplicates in pass 2
    found_ids = {c.conflicting_memory_id for c in conflicts}

    # --- Pass 2: embedding cosine similarity (if both have embeddings) ---
    if memory.embedding is not None:
        try:
            _detect_embedding_conflicts(
                db, memory, borrower_id, org_id,
                conflictable_types, found_ids, conflicts,
            )
        except Exception as e:
            # pgvector may not be available or embeddings may be in wrong format
            logger.warning(
                "Embedding conflict detection failed for memory %s: %s",
                memory.id, e,
            )

    # Sort by similarity descending
    conflicts.sort(key=lambda c: c.similarity_score, reverse=True)

    elapsed_ms = int((time.monotonic() - start_ms) * 1000)
    if conflicts:
        logger.info(
            "Conflict detection for memory %d found %d conflicts in %dms",
            memory.id, len(conflicts), elapsed_ms,
        )

    return conflicts


def _detect_embedding_conflicts(
    db: Session,
    memory: "AgentMemory",
    borrower_id: int,
    org_id: int,
    conflictable_types: set,
    exclude_ids: set,
    conflicts: List[ConflictResult],
) -> None:
    """
    Use pgvector cosine similarity to find semantically similar memories.

    Only returns results with similarity > SIMILARITY_CONFLICT_THRESHOLD.
    """
    # Build the embedding string for the SQL query
    embedding_value = memory.embedding
    if isinstance(embedding_value, list):
        embedding_str = "[" + ",".join(str(v) for v in embedding_value) + "]"
    elif isinstance(embedding_value, str):
        embedding_str = embedding_value
    else:
        # numpy array or pgvector type — convert to string
        embedding_str = str(embedding_value)

    # Build exclusion clause for IDs already matched by fact_key
    exclude_clause = ""
    params = {
        "memory_id": memory.id,
        "borrower_id": borrower_id,
        "org_id": org_id,
        "embedding": embedding_str,
        "threshold": SIMILARITY_CONFLICT_THRESHOLD,
    }

    if exclude_ids:
        exclude_placeholders = ", ".join(
            f":excl_{i}" for i in range(len(exclude_ids))
        )
        for i, eid in enumerate(exclude_ids):
            params[f"excl_{i}"] = eid
        exclude_clause = f"AND am.id NOT IN ({exclude_placeholders})"

    # Build type filter
    type_values = [t.value for t in conflictable_types]
    type_placeholders = ", ".join(f":type_{i}" for i in range(len(type_values)))
    for i, tv in enumerate(type_values):
        params[f"type_{i}"] = tv

    sql = text(f"""
        SELECT
            am.id,
            am.value,
            am.topic,
            am.memory_type,
            1 - (am.embedding <=> CAST(:embedding AS vector)) AS similarity
        FROM agent_memories am
        WHERE am.id != :memory_id
          AND am.borrower_id = :borrower_id
          AND am.organization_id = :org_id
          AND am.superseded_by IS NULL
          AND am.embedding IS NOT NULL
          AND am.memory_type IN ({type_placeholders})
          {exclude_clause}
          AND 1 - (am.embedding <=> CAST(:embedding AS vector)) > :threshold
        ORDER BY similarity DESC
        LIMIT 10
    """)

    rows = db.execute(sql, params).fetchall()

    for row in rows:
        similarity = float(row.similarity)
        same_topic = (
            memory.topic is not None
            and row.topic is not None
            and memory.topic == row.topic
        )

        if similarity > SIMILARITY_AUTO_SUPERSEDE_THRESHOLD and same_topic:
            action = SuggestedAction.SUPERSEDE
        elif similarity > SIMILARITY_CONFLICT_THRESHOLD:
            action = SuggestedAction.FLAG_FOR_REVIEW
        else:
            action = SuggestedAction.KEEP_BOTH

        conflicts.append(ConflictResult(
            conflicting_memory_id=row.id,
            conflicting_memory_value=row.value or "",
            similarity_score=round(similarity, 4),
            match_type="embedding",
            suggested_action=action,
        ))


# ---------------------------------------------------------------------------
# Conflict Resolution
# ---------------------------------------------------------------------------

def resolve_auto_conflicts(
    db: Session,
    new_memory: "AgentMemory",
    conflicts: List[ConflictResult],
) -> dict:
    """
    Automatically resolve conflicts where resolution is safe.

    Rules:
      - fact_key match (SUPERSEDE): auto-supersede older memory, log audit
      - Embedding similarity > 0.92 + same topic (SUPERSEDE): auto-supersede, log audit
      - Embedding similarity 0.85-0.92 (FLAG_FOR_REVIEW): write back to staging
        for admin review
      - KEEP_BOTH: no action

    Returns summary dict with counts of actions taken.
    """
    from database.models.agent_memory import AgentMemory
    from database.models.memory_audit import MemoryAuditEvent
    from database.models.memory_staging import MemoryStaging

    summary = {
        "superseded": 0,
        "flagged_for_review": 0,
        "kept_both": 0,
        "errors": 0,
    }

    for conflict in conflicts:
        try:
            if conflict.suggested_action == SuggestedAction.SUPERSEDE:
                _auto_supersede(
                    db, new_memory, conflict,
                )
                summary["superseded"] += 1

            elif conflict.suggested_action == SuggestedAction.FLAG_FOR_REVIEW:
                _flag_for_review(
                    db, new_memory, conflict,
                )
                summary["flagged_for_review"] += 1

            else:
                summary["kept_both"] += 1

        except Exception as e:
            logger.error(
                "Error resolving conflict between memory %d and %d: %s",
                new_memory.id, conflict.conflicting_memory_id, e,
            )
            summary["errors"] += 1

    if summary["superseded"] > 0 or summary["flagged_for_review"] > 0:
        try:
            db.commit()
        except Exception as e:
            logger.error("Failed to commit conflict resolution: %s", e)
            db.rollback()
            raise

    return summary


def _auto_supersede(
    db: Session,
    new_memory: "AgentMemory",
    conflict: ConflictResult,
) -> None:
    """Mark the conflicting (older) memory as superseded by the new one."""
    from database.models.agent_memory import AgentMemory
    from database.models.memory_audit import MemoryAuditEvent

    old_memory = db.query(AgentMemory).filter(
        AgentMemory.id == conflict.conflicting_memory_id,
    ).first()

    if not old_memory:
        logger.warning(
            "Cannot supersede memory %d — not found",
            conflict.conflicting_memory_id,
        )
        return

    # Already superseded by something else
    if old_memory.superseded_by is not None:
        return

    old_memory.superseded_by = new_memory.id

    audit = MemoryAuditEvent(
        organization_id=new_memory.organization_id,
        borrower_id=new_memory.borrower_id,
        event_type="conflict_auto_supersede",
        memory_id=new_memory.id,
        source_call_id=new_memory.source_call_id,
        details={
            "old_memory_id": conflict.conflicting_memory_id,
            "old_value": conflict.conflicting_memory_value[:200],
            "new_value": (new_memory.value or "")[:200],
            "similarity_score": conflict.similarity_score,
            "match_type": conflict.match_type,
        },
    )
    db.add(audit)


def _flag_for_review(
    db: Session,
    new_memory: "AgentMemory",
    conflict: ConflictResult,
) -> None:
    """
    Create a staging entry flagging the conflict for admin review.

    The admin sees both the new memory and the conflicting one, with
    the similarity score, and can choose to supersede or keep both.
    """
    from database.models.memory_audit import MemoryAuditEvent
    from database.models.memory_staging import MemoryStaging

    # Write a staging item so admins see the conflict in the review queue
    staging = MemoryStaging(
        organization_id=new_memory.organization_id or 0,
        borrower_id=new_memory.borrower_id or 0,
        source_call_id=new_memory.source_call_id or "conflict_detection",
        fact_text=(
            f"CONFLICT: New memory \"{(new_memory.value or '')[:100]}\" "
            f"may contradict existing memory \"{conflict.conflicting_memory_value[:100]}\" "
            f"(similarity: {conflict.similarity_score:.2f})"
        ),
        fact_type=new_memory.memory_type.value if hasattr(new_memory.memory_type, "value") else str(new_memory.memory_type),
        topic=new_memory.topic,
        confidence=conflict.similarity_score,
        fact_key=new_memory.fact_key,
        destination="memory",
        status="pending_review",
    )
    db.add(staging)

    audit = MemoryAuditEvent(
        organization_id=new_memory.organization_id,
        borrower_id=new_memory.borrower_id,
        event_type="conflict_flagged_for_review",
        memory_id=new_memory.id,
        source_call_id=new_memory.source_call_id,
        details={
            "conflicting_memory_id": conflict.conflicting_memory_id,
            "conflicting_value": conflict.conflicting_memory_value[:200],
            "new_value": (new_memory.value or "")[:200],
            "similarity_score": conflict.similarity_score,
            "match_type": conflict.match_type,
        },
    )
    db.add(audit)


# ---------------------------------------------------------------------------
# Confidence Decay
# ---------------------------------------------------------------------------

def apply_confidence_decay(
    db: Session,
    organization_id: Optional[int] = None,
) -> dict:
    """
    Decay confidence on memories whose last_verified_at is stale.

    Thresholds:
      - > 90 days since verification:  confidence *= 0.9
      - > 180 days since verification: confidence *= 0.7

    DIRECTIVE type is exempt (explicit user instructions don't decay).

    Can be scoped to a single org or run globally (organization_id=None).
    Called from refresh_agent_memory_scores in learning_tasks.py.

    Returns dict with counts of decayed memories.
    """
    from database.models.agent_memory import AgentMemory, MemoryType

    start_ms = time.monotonic()
    now = datetime.now(timezone.utc)
    cutoff_90 = now - timedelta(days=90)
    cutoff_180 = now - timedelta(days=180)

    # Base filter: non-superseded, non-directive, has last_verified_at
    base_filter = [
        AgentMemory.superseded_by.is_(None),
        AgentMemory.memory_type != MemoryType.DIRECTIVE.value,
        AgentMemory.last_verified_at.isnot(None),
    ]

    if organization_id is not None:
        base_filter.append(AgentMemory.organization_id == organization_id)

    # --- Tier 1: 90-180 days old -> multiply by 0.9 ---
    tier1_memories = (
        db.query(AgentMemory)
        .filter(
            *base_filter,
            AgentMemory.last_verified_at < cutoff_90,
            AgentMemory.last_verified_at >= cutoff_180,
            AgentMemory.confidence > 0.1,  # Don't decay already-low memories
        )
        .all()
    )

    tier1_count = 0
    for mem in tier1_memories:
        old_conf = mem.confidence or 1.0
        new_conf = round(old_conf * DECAY_90_DAY_MULTIPLIER, 4)
        if new_conf != old_conf:
            mem.confidence = max(new_conf, 0.05)  # Floor at 0.05
            tier1_count += 1

    # --- Tier 2: > 180 days old -> multiply by 0.7 ---
    tier2_memories = (
        db.query(AgentMemory)
        .filter(
            *base_filter,
            AgentMemory.last_verified_at < cutoff_180,
            AgentMemory.confidence > 0.1,
        )
        .all()
    )

    tier2_count = 0
    for mem in tier2_memories:
        old_conf = mem.confidence or 1.0
        new_conf = round(old_conf * DECAY_180_DAY_MULTIPLIER, 4)
        if new_conf != old_conf:
            mem.confidence = max(new_conf, 0.05)  # Floor at 0.05
            tier2_count += 1

    try:
        db.commit()
    except Exception as e:
        logger.error("Failed to commit confidence decay: %s", e)
        db.rollback()
        raise

    elapsed_ms = int((time.monotonic() - start_ms) * 1000)
    total = tier1_count + tier2_count

    if total > 0:
        logger.info(
            "Confidence decay applied: %d memories (tier1=%d, tier2=%d) in %dms%s",
            total, tier1_count, tier2_count, elapsed_ms,
            f" for org {organization_id}" if organization_id else "",
        )

    return {
        "tier1_decayed_90d": tier1_count,
        "tier2_decayed_180d": tier2_count,
        "total_decayed": total,
        "elapsed_ms": elapsed_ms,
    }
