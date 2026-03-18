"""
Agent Memory Models

Persistent memory system for AI agents — stores conversation summaries,
learned facts/preferences, and shared cross-session context.

Three tables:
    - agent_conversations: Completed conversation sessions with summary
    - agent_memories: Individual facts, preferences, and context snippets
      extracted from conversations (can have TTL via expires_at)
    - agent_contexts: Lightweight key-value store for per-user/org settings
      and state that agents reference across sessions

Design goals:
    - Opt-in per agent role (caller decides whether to persist)
    - Multi-tenant isolation via organization_id
    - Automatic expiry support for transient memories
    - Confidence scoring so agents can weigh memories appropriately

Usage:
    from database.models.agent_memory import (
        AgentConversation, AgentMemory, AgentContext,
        MemoryType,
    )
"""

import enum
import logging
from datetime import datetime, timezone

from sqlalchemy import (
    Column, Integer, String, DateTime, Text, Float,
    ForeignKey, Index, JSON,
    Enum as SAEnum,
)
from sqlalchemy.orm import relationship

from db import Base

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class MemoryType(str, enum.Enum):
    """Classification of a stored memory."""
    FACT = "fact"              # Objective information (e.g. "borrower credit score is 740")
    PREFERENCE = "preference"  # User preference (e.g. "prefers email over phone")
    CONTEXT = "context"        # Situational context (e.g. "currently working on refi")
    INSIGHT = "insight"        # Agent-derived insight (e.g. "lead responds best on Tuesdays")
    DIRECTIVE = "directive"    # Explicit instruction from user (e.g. "always show rates first")


# ---------------------------------------------------------------------------
# Agent Conversations
# ---------------------------------------------------------------------------

class AgentConversation(Base):
    """
    Represents a completed (or in-progress) conversation between a user
    and an AI agent.  Stores the summarised version of the exchange so that
    future sessions can recall what was discussed.
    """
    __tablename__ = "agent_conversations"
    __table_args__ = (
        Index("ix_agent_conv_user_org", "user_id", "organization_id"),
        Index("ix_agent_conv_role", "agent_role"),
        Index("ix_agent_conv_started", "started_at"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    organization_id = Column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # Which agent role handled the conversation (e.g. "pipeline_analyst", "compliance_checker")
    agent_role = Column(String(100), nullable=False)

    # Timestamps
    started_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    ended_at = Column(DateTime, nullable=True)

    # AI-generated summary of the entire conversation
    summary = Column(Text, nullable=True)

    # Optional: structured key points extracted by the agent
    key_points = Column(JSON, nullable=True)

    # How many user messages were in the conversation
    message_count = Column(Integer, default=0)

    # Relationship to extracted memories
    memories = relationship(
        "AgentMemory",
        back_populates="conversation",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


# ---------------------------------------------------------------------------
# Agent Memories
# ---------------------------------------------------------------------------

class AgentMemory(Base):
    """
    An individual memory extracted from a conversation or explicitly saved.
    Memories have a type, a key/value pair, a confidence score, and an
    optional expiry.
    """
    __tablename__ = "agent_memories"
    __table_args__ = (
        Index("ix_agent_mem_user_org", "user_id", "organization_id"),
        Index("ix_agent_mem_type", "memory_type"),
        Index("ix_agent_mem_key", "key"),
        Index("ix_agent_mem_expires", "expires_at"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True)

    # Link to the conversation that produced this memory (nullable for
    # memories saved outside a conversation)
    conversation_id = Column(
        Integer,
        ForeignKey("agent_conversations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    organization_id = Column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # Classification
    memory_type = Column(
        SAEnum(MemoryType, name="memory_type_enum", create_constraint=False),
        nullable=False,
        default=MemoryType.FACT,
    )

    # Key-value payload.  `key` is a short machine-friendly label
    # (e.g. "preferred_contact_method"), `value` is the content.
    key = Column(String(255), nullable=False)
    value = Column(Text, nullable=False)

    # How confident the agent is in this memory (0.0 - 1.0)
    confidence = Column(Float, default=1.0)

    # Which agent role created this memory
    agent_role = Column(String(100), nullable=True)

    # Lifecycle
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    expires_at = Column(DateTime, nullable=True)  # NULL = never expires

    # Relationship back to conversation
    conversation = relationship("AgentConversation", back_populates="memories")


# ---------------------------------------------------------------------------
# Agent Context (lightweight key-value store)
# ---------------------------------------------------------------------------

class AgentContext(Base):
    """
    Persistent key-value context that agents can read/write across sessions.

    Unlike AgentMemory (which is tied to conversations and has confidence
    scores), AgentContext is a simple store for things like:
        - last_pipeline_view: "underwriting"
        - default_report_period: "30"
        - working_loan_id: "abc-123"

    Scoped per user + organization.
    """
    __tablename__ = "agent_contexts"
    __table_args__ = (
        Index("ix_agent_ctx_user_org", "user_id", "organization_id"),
        Index("ix_agent_ctx_key", "context_key"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    organization_id = Column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    context_key = Column(String(255), nullable=False)
    context_value = Column(Text, nullable=True)

    last_updated = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
