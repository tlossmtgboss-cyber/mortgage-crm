"""
Memory Configuration Models

MemoryTopicConfig — controls which topics load for Tier 1 context
based on call trigger and loan stage.

MemoryExclusionRule — exclusion list for the consolidation pipeline.
Updated without a deploy.
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Column, Integer, String, DateTime, Text, Boolean,
    ForeignKey, Index,
)
from sqlalchemy.dialects.postgresql import JSONB

from db import Base


class MemoryTopicConfig(Base):
    __tablename__ = "memory_topic_config"
    __table_args__ = (
        Index("ix_topic_config_trigger", "call_trigger"),
        Index("ix_topic_config_org", "organization_id"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True)
    call_trigger = Column(String(50), nullable=False)
    loan_stage = Column(String(50), nullable=True)
    topics = Column(JSONB, nullable=False)
    priority = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))


class MemoryExclusionRule(Base):
    __tablename__ = "memory_exclusion_rules"
    __table_args__ = (
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True)
    category = Column(String(100), nullable=False)
    pattern = Column(Text, nullable=False)
    transformation = Column(Text, nullable=True)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
