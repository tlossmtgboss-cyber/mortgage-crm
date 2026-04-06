"""
Agent Context Store — Continual Learning (Domain 8)

Persists learned context per agent/user/branch, captures correction events
in real time, and maintains an immutable audit log for all context mutations.

Models:
    AgentContextStore   — Learned context (scoped to agent/user/branch/org)
    AgentContextEvent   — Real-time corrections, approvals, overrides, feedback
    ContextChangeAudit  — Immutable audit trail for every context mutation

Usage:
    from database.models.agent_context import (
        AgentContextStore, AgentContextEvent, ContextChangeAudit,
    )
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Text,
    ForeignKey, JSON, Index, UniqueConstraint,
)

from db import Base


# ============================================================================
# AGENT CONTEXT STORE — Persisted learned context per scope
# ============================================================================

class AgentContextStore(Base):
    """Persists learned context per agent/user/branch/org."""
    __tablename__ = "agent_context_store"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    scope = Column(String, nullable=False)  # 'agent' | 'user' | 'branch' | 'org'
    scope_id = Column(String, nullable=False, index=True)  # agent_id | user_id | branch_id | org_id
    context_key = Column(String, nullable=False)  # e.g. 'underwriting_preferences'
    context_value = Column(JSON, nullable=False)  # structured learned context
    source = Column(String, nullable=False)  # 'hot_path' | 'offline_consolidation' | 'manual'
    confidence = Column(Float)  # 0.0-1.0
    version = Column(Integer, default=1)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index('ix_context_store_scope', 'scope', 'scope_id'),
        UniqueConstraint('scope', 'scope_id', 'context_key', name='uq_context_scope_key'),
    )


# ============================================================================
# AGENT CONTEXT EVENT — Real-time corrections/approvals
# ============================================================================

class AgentContextEvent(Base):
    """Captures corrections, approvals, overrides, and feedback in real time."""
    __tablename__ = "agent_context_events"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    agent_id = Column(String, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    file_id = Column(Integer, nullable=True)  # loan file if applicable
    event_type = Column(String, nullable=False)  # 'correction' | 'approval' | 'override' | 'feedback'
    original_output = Column(JSON, nullable=True)
    corrected_value = Column(JSON, nullable=True)
    rationale = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ============================================================================
# CONTEXT CHANGE AUDIT — Immutable audit log for all context mutations
# ============================================================================

class ContextChangeAudit(Base):
    """Immutable audit log for every context store mutation."""
    __tablename__ = "context_change_audit"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    scope = Column(String, nullable=False)
    scope_id = Column(String, nullable=False)
    context_key = Column(String, nullable=False)
    previous_value = Column(JSON, nullable=True)
    new_value = Column(JSON, nullable=True)
    change_source = Column(String, nullable=False)  # 'hot_path' | 'consolidation' | 'manual' | 'rollback'
    triggered_by = Column(String, nullable=True)  # job name or user_id
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
