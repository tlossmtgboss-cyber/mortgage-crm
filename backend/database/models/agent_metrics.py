"""
Agent Performance Metrics Models

Tracks AI agent invocations — which agent, which tool, duration, status,
token usage, and estimated cost.  Powers the admin agent-metrics dashboard.

Tables:
- agent_invocations: One row per agent tool call (append-only log)

Usage:
    from database.models.agent_metrics import AgentInvocation

    invocation = AgentInvocation(
        agent_role="pipeline_analyst",
        tool_name="get_pipeline_metrics",
        user_id=42,
        organization_id=1,
        duration_ms=312,
        status="success",
    )
    db.add(invocation)
    db.commit()
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, DateTime, Text, ForeignKey, Index, Numeric,
)

from db import Base


class AgentInvocation(Base):
    """
    Append-only log of AI agent tool invocations.

    Each row represents a single tool call made by an AI agent on behalf of
    a user.  Used for performance monitoring, cost tracking, and error
    analysis.
    """
    __tablename__ = "agent_invocations"
    __table_args__ = (
        Index("ix_agent_inv_org_created", "organization_id", "created_at"),
        Index("ix_agent_inv_role", "agent_role"),
        Index("ix_agent_inv_tool", "tool_name"),
        Index("ix_agent_inv_status", "status"),
        Index("ix_agent_inv_created", "created_at"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True)

    # Who invoked it
    agent_role = Column(String(100), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)

    # What was invoked
    tool_name = Column(String(200), nullable=False, index=True)

    # Timing
    started_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime, nullable=True)
    duration_ms = Column(Integer, nullable=True)  # Wall-clock milliseconds

    # Outcome
    status = Column(String(20), nullable=False, default="success")  # success | error | timeout
    error_message = Column(Text, nullable=True)

    # Token / cost tracking (nullable — not every invocation has token info)
    tokens_used = Column(Integer, nullable=True)
    cost_estimate = Column(Numeric(10, 6), nullable=True)  # USD, six decimal places

    # Bookkeeping
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Table creation helper (called from main.py at startup)
# ---------------------------------------------------------------------------

def create_tables_if_needed(engine):
    """Create the agent_invocations table if it doesn't exist."""
    AgentInvocation.__table__.create(engine, checkfirst=True)
