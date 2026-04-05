"""
Agent Feedback Models

Stores user feedback (thumbs up/down/neutral) on AI agent responses so the
system can learn from interactions and surface quality trends per agent role.

Tables:
- agent_feedback: One row per user rating on an AI response (append-only)
- agent_feedback_summaries: Aggregated feedback metrics per agent role per period

Usage:
    from database.models.agent_feedback import AgentFeedback, AgentFeedbackSummary

    # Record individual feedback
    fb = AgentFeedback(
        organization_id=1,
        user_id=42,
        conversation_id="conv_abc123",
        message_index=3,
        rating="positive",
        agent_role="pipeline_analyst",
        intent="get_pipeline_metrics",
    )
    db.add(fb)
    db.commit()

    # Query aggregated summaries
    summaries = db.query(AgentFeedbackSummary).filter_by(
        organization_id=1, agent_role="pipeline_analyst"
    ).all()
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, DateTime, Text, JSON, ForeignKey, Index,
)

from db import Base


class AgentFeedback(Base):
    """
    Append-only log of user feedback on individual AI agent responses.

    Each row represents a single thumbs-up / thumbs-down / neutral rating
    that a user gave to an AI response within a conversation.  Used to
    identify poorly-performing agents, popular intents, and areas for
    prompt improvement.
    """
    __tablename__ = "agent_feedback"
    __table_args__ = (
        Index("ix_agent_fb_org_role", "organization_id", "agent_role"),
        Index("ix_agent_fb_org_created", "organization_id", "created_at"),
        Index("ix_agent_fb_conv", "conversation_id"),
        Index("ix_agent_fb_rating", "rating"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True)

    # Tenant + user
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # Conversation context
    conversation_id = Column(String(100), nullable=False, index=True)
    message_index = Column(Integer, nullable=True)

    # The feedback itself
    rating = Column(String(20), nullable=False)  # 'positive', 'negative', 'neutral'
    feedback_text = Column(Text, nullable=True)

    # Agent context
    agent_role = Column(String(100), nullable=True, index=True)
    intent = Column(String(100), nullable=True, index=True)

    # Captured request/response for replay & analysis
    query_text = Column(Text, nullable=True)
    response_text = Column(Text, nullable=True)
    tools_used = Column(JSON, nullable=True)

    # Performance snapshot at time of feedback
    response_time_ms = Column(Integer, nullable=True)
    token_count = Column(Integer, nullable=True)

    # Bookkeeping
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


class AgentFeedbackSummary(Base):
    """
    Aggregated feedback metrics per agent role per time period.

    Built by a periodic roll-up job that buckets AgentFeedback rows into
    daily/weekly/monthly windows.  Powers the admin feedback-trends
    dashboard without requiring expensive real-time aggregation queries.
    """
    __tablename__ = "agent_feedback_summaries"
    __table_args__ = (
        Index("ix_agent_fbs_org_role", "organization_id", "agent_role"),
        Index("ix_agent_fbs_org_period", "organization_id", "period_start"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True)

    # Tenant
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)

    # Aggregation dimensions
    agent_role = Column(String(100), nullable=False, index=True)
    period_start = Column(DateTime, nullable=False)
    period_end = Column(DateTime, nullable=False)

    # Counts
    total_interactions = Column(Integer, nullable=False, default=0)
    positive_count = Column(Integer, nullable=False, default=0)
    negative_count = Column(Integer, nullable=False, default=0)

    # Averages
    avg_response_time_ms = Column(Integer, nullable=True)
    avg_token_count = Column(Integer, nullable=True)

    # Qualitative roll-ups (JSON blobs)
    top_intents = Column(JSON, nullable=True)          # e.g. [{"intent": "...", "count": N}, ...]
    common_complaints = Column(JSON, nullable=True)    # recurring negative feedback themes
    improvement_suggestions = Column(JSON, nullable=True)

    # Bookkeeping
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Table creation helper (called from main.py at startup)
# ---------------------------------------------------------------------------

def create_tables_if_needed(engine):
    """Create the agent_feedback and agent_feedback_summaries tables if they don't exist."""
    AgentFeedback.__table__.create(engine, checkfirst=True)
    AgentFeedbackSummary.__table__.create(engine, checkfirst=True)
