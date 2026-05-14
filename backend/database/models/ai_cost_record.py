"""
AI Cost Record Model

Persistent storage for AI API cost tracking. Each row represents a single
AI API call with its token counts, calculated dollar cost, and metadata.

Powers the AI cost dashboard, budget alerts, and per-org/per-agent cost
reporting.

Tables:
- ai_cost_records: One row per AI API call (append-only log)

Usage:
    from database.models.ai_cost_record import AICostRecord

    record = AICostRecord(
        organization_id=1,
        user_id=42,
        agent_type="pipeline_analyst",
        model="claude-sonnet-4-6",
        input_tokens=1500,
        output_tokens=800,
        cost_usd=Decimal("0.016500"),
        duration_ms=312,
    )
    db.add(record)
    db.commit()
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
)
from sqlalchemy.dialects.postgresql import UUID

from db import Base


class AICostRecord(Base):
    """
    Append-only log of AI API calls with dollar-cost tracking.

    Each row represents one AI API call (Anthropic, OpenAI, etc.) with
    the exact token counts and computed cost in USD. Used for:
    - Per-org daily/monthly cost reporting
    - Per-agent-type cost breakdown
    - Budget threshold alerts
    - Platform-wide cost analytics
    """

    __tablename__ = "ai_cost_records"

    __table_args__ = (
        # Primary query: org costs over time range
        Index("ix_ai_cost_org_created", "organization_id", "created_at"),
        # Agent-type breakdown within an org
        Index("ix_ai_cost_org_agent", "organization_id", "agent_type"),
        # Model-level cost analysis
        Index("ix_ai_cost_model", "model"),
        # Time-series queries (daily rollups, trend analysis)
        Index("ix_ai_cost_created", "created_at"),
        # User-level cost tracking
        Index("ix_ai_cost_user", "user_id", "created_at"),
        {"extend_existing": True},
    )

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Tenant isolation
    organization_id = Column(
        Integer,
        ForeignKey("organizations.id"),
        nullable=False,
        index=True,
    )

    # Who triggered the AI call (nullable for system-initiated calls)
    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=True,
    )

    # Which AI agent handled this
    agent_type = Column(String(64), nullable=False)  # e.g. "pipeline_analyst", "compliance_checker"

    # Model used
    model = Column(String(64), nullable=False)  # e.g. "claude-sonnet-4-6", "claude-haiku-4-5-20251001"

    # Token counts
    input_tokens = Column(Integer, nullable=False)
    output_tokens = Column(Integer, nullable=False)

    # Dollar cost (Numeric for precision -- never float for money)
    cost_usd = Column(Numeric(10, 6), nullable=False)

    # Latency
    duration_ms = Column(Integer, nullable=True)

    # Timestamps
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Table creation helper (called from start.py or main.py at startup)
# ---------------------------------------------------------------------------

def create_tables_if_needed(engine):
    """Create the ai_cost_records table if it doesn't exist."""
    AICostRecord.__table__.create(engine, checkfirst=True)


__all__ = ["AICostRecord", "create_tables_if_needed"]
