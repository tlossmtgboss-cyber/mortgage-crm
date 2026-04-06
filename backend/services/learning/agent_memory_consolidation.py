"""
Agent Memory Consolidation Job — Continual Learning (Domain 8)

Nightly job (runs at 2 AM) that consolidates the past 24 hours of
agent_context_events into durable learned context in agent_context_store.

Pipeline:
    1. Pull last 24h of agent_context_events per active agent
    2. Identify patterns: repeated corrections, ignored suggestions,
       high-confidence approved outputs
    3. Generate context-update proposals via ContextSynthesisAgent
    4. Write approved updates to agent_context_store
    5. Log every mutation to context_change_audit (immutable)
"""

import logging
import os
import uuid
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import and_, func

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy model imports (avoids circular imports at module load time)
# ---------------------------------------------------------------------------

_models_loaded = False
_AgentContextStore = None
_AgentContextEvent = None
_ContextChangeAudit = None


def _ensure_models():
    """Load models on first use."""
    global _models_loaded, _AgentContextStore, _AgentContextEvent, _ContextChangeAudit
    if _models_loaded:
        return
    from database.models.agent_context import (
        AgentContextStore,
        AgentContextEvent,
        ContextChangeAudit,
    )
    _AgentContextStore = AgentContextStore
    _AgentContextEvent = AgentContextEvent
    _ContextChangeAudit = ContextChangeAudit
    _models_loaded = True


# ---------------------------------------------------------------------------
# Pattern detection helpers
# ---------------------------------------------------------------------------

class _PatternCluster:
    """Groups related context events into a learnable pattern."""

    __slots__ = ("event_type", "context_key", "events", "frequency", "consistency")

    def __init__(self, event_type: str, context_key: str):
        self.event_type = event_type
        self.context_key = context_key
        self.events: List[dict] = []
        self.frequency: int = 0
        self.consistency: float = 0.0

    def add(self, event_row: dict) -> None:
        self.events.append(event_row)
        self.frequency = len(self.events)

    def compute_consistency(self) -> float:
        """How consistent are corrected_value entries across events."""
        if self.frequency < 2:
            self.consistency = 1.0
            return self.consistency
        values = [
            str(e.get("corrected_value", ""))
            for e in self.events
            if e.get("corrected_value") is not None
        ]
        if not values:
            self.consistency = 0.0
            return self.consistency
        most_common = max(set(values), key=values.count)
        self.consistency = values.count(most_common) / len(values)
        return self.consistency


def _cluster_events(events: List[dict]) -> List[_PatternCluster]:
    """Group events by (event_type, inferred context_key) for pattern analysis."""
    buckets: Dict[str, _PatternCluster] = {}
    for ev in events:
        event_type = ev.get("event_type", "unknown")
        # Derive a context_key from original/corrected output structure
        context_key = _infer_context_key(ev)
        key = f"{event_type}::{context_key}"
        if key not in buckets:
            buckets[key] = _PatternCluster(event_type, context_key)
        buckets[key].add(ev)

    clusters = list(buckets.values())
    for c in clusters:
        c.compute_consistency()
    return clusters


def _infer_context_key(event: dict) -> str:
    """Best-effort derivation of a context key from event payload."""
    original = event.get("original_output") or {}
    corrected = event.get("corrected_value") or {}
    # If either payload carries an explicit key, use it
    for payload in (corrected, original):
        if isinstance(payload, dict) and "context_key" in payload:
            return payload["context_key"]
    # Fall back to event_type
    return event.get("event_type", "general")


# ---------------------------------------------------------------------------
# AgentMemoryConsolidationJob
# ---------------------------------------------------------------------------

class AgentMemoryConsolidationJob:
    """Nightly job that consolidates agent learning from the past 24 hours.

    Designed to run inside an async scheduler (e.g. APScheduler) or as a
    standalone invocation from a management command.
    """

    MIN_EVENTS_THRESHOLD = 5  # Need at least 5 events to learn from
    HIGH_CONFIDENCE_THRESHOLD = 0.75
    LOOKBACK_HOURS = 24
    JOB_NAME = "agent_memory_consolidation"

    def __init__(self, db: Session):
        self.db = db
        self.anthropic_key = os.getenv("ANTHROPIC_API_KEY")

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def run(self) -> dict:
        """Process all active agents. Returns a summary dict."""
        _ensure_models()
        cutoff = datetime.now(timezone.utc) - timedelta(hours=self.LOOKBACK_HOURS)

        # Distinct agent_ids that have events in the window
        agent_ids = (
            self.db.query(_AgentContextEvent.agent_id)
            .filter(_AgentContextEvent.created_at >= cutoff)
            .distinct()
            .all()
        )
        agent_ids = [row[0] for row in agent_ids]

        summary: Dict[str, Any] = {
            "job": self.JOB_NAME,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "agents_evaluated": len(agent_ids),
            "agents_updated": 0,
            "total_context_writes": 0,
            "errors": [],
        }

        for agent_id in agent_ids:
            try:
                result = await self.consolidate_agent(agent_id, cutoff)
                if result.get("updates_written", 0) > 0:
                    summary["agents_updated"] += 1
                    summary["total_context_writes"] += result["updates_written"]
            except Exception as e:
                logger.exception("Consolidation failed for agent %s", agent_id)
                summary["errors"].append({"agent_id": agent_id, "error": str(e)})

        summary["finished_at"] = datetime.now(timezone.utc).isoformat()
        logger.info(
            "Memory consolidation complete: %d agents, %d updates",
            summary["agents_evaluated"],
            summary["total_context_writes"],
        )
        return summary

    # ------------------------------------------------------------------
    # Per-agent consolidation
    # ------------------------------------------------------------------

    async def consolidate_agent(
        self, agent_id: str, cutoff: Optional[datetime] = None
    ) -> dict:
        """Consolidate learning for a single agent.

        Returns dict with keys: agent_id, events_found, clusters, updates_written.
        """
        _ensure_models()
        if cutoff is None:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=self.LOOKBACK_HOURS)

        # 1. Pull recent events
        rows = (
            self.db.query(_AgentContextEvent)
            .filter(
                and_(
                    _AgentContextEvent.agent_id == agent_id,
                    _AgentContextEvent.created_at >= cutoff,
                )
            )
            .order_by(_AgentContextEvent.created_at.asc())
            .all()
        )
        events = [
            {
                "id": r.id,
                "agent_id": r.agent_id,
                "user_id": r.user_id,
                "file_id": r.file_id,
                "event_type": r.event_type,
                "original_output": r.original_output,
                "corrected_value": r.corrected_value,
                "rationale": r.rationale,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]

        result = {
            "agent_id": agent_id,
            "events_found": len(events),
            "clusters": 0,
            "updates_written": 0,
        }

        # 2. Skip if below threshold
        if len(events) < self.MIN_EVENTS_THRESHOLD:
            logger.debug(
                "Agent %s has %d events (< %d threshold), skipping",
                agent_id, len(events), self.MIN_EVENTS_THRESHOLD,
            )
            return result

        # 3. Cluster events by pattern
        clusters = _cluster_events(events)
        result["clusters"] = len(clusters)

        # 4. Synthesize learned preferences
        synthesis = await self._synthesize_context(agent_id, events, clusters)
        if not synthesis or not synthesis.get("learned_preferences"):
            return result

        # 5. Write approved context updates
        learned = synthesis["learned_preferences"]
        confidence = synthesis.get("confidence", 0.0)

        if confidence < self.HIGH_CONFIDENCE_THRESHOLD:
            logger.info(
                "Agent %s synthesis confidence %.2f below threshold %.2f, skipping write",
                agent_id, confidence, self.HIGH_CONFIDENCE_THRESHOLD,
            )
            return result

        for key, value in learned.items():
            await self._upsert_context(
                scope="agent",
                scope_id=agent_id,
                key=key,
                value=value,
                source="offline_consolidation",
                confidence=confidence,
            )
            result["updates_written"] += 1

        return result

    # ------------------------------------------------------------------
    # Context synthesis via LLM
    # ------------------------------------------------------------------

    async def _synthesize_context(
        self, agent_id: str, events: list, clusters: List[_PatternCluster]
    ) -> dict:
        """Use Claude to extract learnable patterns from event clusters.

        Falls back to heuristic-only extraction if no API key is configured.
        """
        from services.learning.context_synthesis_agent import ContextSynthesisAgent

        agent = ContextSynthesisAgent(anthropic_key=self.anthropic_key)
        return await agent.synthesize(agent_id, events, clusters)

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    async def _upsert_context(
        self,
        scope: str,
        scope_id: str,
        key: str,
        value: Any,
        source: str,
        confidence: float = 1.0,
    ) -> None:
        """Write to agent_context_store with audit logging."""
        _ensure_models()

        existing = (
            self.db.query(_AgentContextStore)
            .filter(
                and_(
                    _AgentContextStore.scope == scope,
                    _AgentContextStore.scope_id == scope_id,
                    _AgentContextStore.context_key == key,
                )
            )
            .first()
        )

        previous_value = None
        if existing:
            previous_value = existing.context_value
            existing.context_value = value
            existing.source = source
            existing.confidence = confidence
            existing.version = (existing.version or 1) + 1
            existing.updated_at = datetime.now(timezone.utc)
        else:
            new_entry = _AgentContextStore(
                id=str(uuid.uuid4()),
                scope=scope,
                scope_id=scope_id,
                context_key=key,
                context_value=value,
                source=source,
                confidence=confidence,
                version=1,
            )
            self.db.add(new_entry)

        self.db.flush()

        # Always audit
        await self._audit_log(
            scope=scope,
            scope_id=scope_id,
            key=key,
            prev=previous_value,
            new=value,
            source=source,
            triggered_by=self.JOB_NAME,
        )
        self.db.commit()

    async def _audit_log(
        self,
        scope: str,
        scope_id: str,
        key: str,
        prev: Any,
        new: Any,
        source: str,
        triggered_by: str,
    ) -> None:
        """Immutable audit record in context_change_audit."""
        _ensure_models()
        record = _ContextChangeAudit(
            id=str(uuid.uuid4()),
            scope=scope,
            scope_id=scope_id,
            context_key=key,
            previous_value=prev,
            new_value=new,
            change_source=source,
            triggered_by=triggered_by,
        )
        self.db.add(record)
        # Caller (upsert_context) handles commit
