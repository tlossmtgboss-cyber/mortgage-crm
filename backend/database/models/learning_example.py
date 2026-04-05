"""
AI Learning System Persistent Models

Stores training examples, discovered patterns, and prompt optimizations that
the AI learning system uses to improve over time.  Replaces the previous
in-memory-only approach so learning survives restarts and can be queried
across the fleet.

Tables:
- learning_examples:    Individual training examples derived from interactions
- learning_patterns:    Discovered behavioral / query patterns
- prompt_optimizations: Tracked prompt changes and their measured impact

Usage:
    from database.models.learning_example import (
        LearningExample, LearningPattern, PromptOptimization,
    )

    ex = LearningExample(
        organization_id=1,
        example_type="positive",
        intent="check_pipeline",
        agent_role="pipeline_analyst",
        query_text="How many loans close this month?",
        expected_response="You have 14 loans...",
        quality_score=92.5,
    )
    db.add(ex)
    db.commit()
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, DateTime, Text, Boolean, JSON,
    ForeignKey, Index, Numeric,
)

from db import Base


# ---------------------------------------------------------------------------
# LearningExample
# ---------------------------------------------------------------------------

class LearningExample(Base):
    """
    A single training example derived from a real interaction.

    Examples are linked back to the feedback that created them (when
    applicable) and carry a quality score so the few-shot selector can
    prioritize the best ones.
    """
    __tablename__ = "learning_examples"
    __table_args__ = (
        Index("ix_lex_org_type", "organization_id", "example_type"),
        Index("ix_lex_intent_role", "intent", "agent_role"),
        Index("ix_lex_active_quality", "is_active", "quality_score"),
        Index("ix_lex_created", "created_at"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True)

    # Scope — null organization_id means global example
    organization_id = Column(
        Integer, ForeignKey("organizations.id"), nullable=True, index=True,
    )

    # Classification
    example_type = Column(
        String(30), nullable=False, index=True,
    )  # positive | negative | correction | few_shot
    intent = Column(String(100), nullable=True, index=True)
    agent_role = Column(String(100), nullable=True, index=True)

    # Content
    query_text = Column(Text, nullable=False)
    expected_response = Column(Text, nullable=True)
    actual_response = Column(Text, nullable=True)
    tools_used = Column(JSON, nullable=True)
    correction_notes = Column(Text, nullable=True)

    # Provenance
    feedback_id = Column(
        Integer, ForeignKey("agent_feedback.id"), nullable=True,
    )

    # Quality & usage
    quality_score = Column(Numeric(5, 2), nullable=True)  # 0-100
    is_active = Column(Boolean, nullable=False, default=True)
    usage_count = Column(Integer, nullable=False, default=0)
    last_used_at = Column(DateTime, nullable=True)

    # Bookkeeping
    created_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime, nullable=True, onupdate=lambda: datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# LearningPattern
# ---------------------------------------------------------------------------

class LearningPattern(Base):
    """
    A discovered pattern in user behaviour or query structure.

    Patterns are identified by (pattern_type, pattern_key) and accumulate
    an occurrence_count and confidence score over time.
    """
    __tablename__ = "learning_patterns"
    __table_args__ = (
        Index("ix_lp_org_type", "organization_id", "pattern_type"),
        Index("ix_lp_type_key", "pattern_type", "pattern_key"),
        Index("ix_lp_active_confidence", "is_active", "confidence"),
        Index("ix_lp_last_seen", "last_seen_at"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True)

    # Scope
    organization_id = Column(
        Integer, ForeignKey("organizations.id"), nullable=True, index=True,
    )

    # Pattern identification
    pattern_type = Column(
        String(50), nullable=False, index=True,
    )  # query_pattern | tool_sequence | intent_mapping | error_pattern
    pattern_key = Column(String(255), nullable=False)
    pattern_value = Column(Text, nullable=False)

    # Strength
    confidence = Column(Numeric(5, 4), nullable=False, default=1.0)  # 0-1
    occurrence_count = Column(Integer, nullable=False, default=1)
    last_seen_at = Column(DateTime, nullable=True)

    # Extra data
    extra_metadata = Column("metadata", JSON, nullable=True)

    # Lifecycle
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime, nullable=True, onupdate=lambda: datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# PromptOptimization
# ---------------------------------------------------------------------------

class PromptOptimization(Base):
    """
    Records a prompt change for a specific agent role, together with before/
    after feedback scores so the impact can be measured.
    """
    __tablename__ = "prompt_optimizations"
    __table_args__ = (
        Index("ix_po_role_type", "agent_role", "optimization_type"),
        Index("ix_po_active", "is_active"),
        Index("ix_po_applied", "applied_at"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True)

    # Target
    agent_role = Column(String(100), nullable=False, index=True)
    optimization_type = Column(
        String(50), nullable=True,
    )  # system_prompt | few_shot | tool_description | intent_pattern

    # Change payload
    previous_value = Column(Text, nullable=True)
    new_value = Column(Text, nullable=True)
    reason = Column(Text, nullable=True)

    # Measured impact
    feedback_score_before = Column(Numeric(5, 2), nullable=True)
    feedback_score_after = Column(Numeric(5, 2), nullable=True)

    # Lifecycle
    is_active = Column(Boolean, nullable=False, default=True)
    applied_at = Column(DateTime, nullable=True)
    rolled_back_at = Column(DateTime, nullable=True)

    # Bookkeeping
    created_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Table creation helper (called from main.py at startup)
# ---------------------------------------------------------------------------

def create_tables_if_needed(engine):
    """Create learning_examples, learning_patterns, and prompt_optimizations
    tables if they don't already exist."""
    LearningExample.__table__.create(engine, checkfirst=True)
    LearningPattern.__table__.create(engine, checkfirst=True)
    PromptOptimization.__table__.create(engine, checkfirst=True)
