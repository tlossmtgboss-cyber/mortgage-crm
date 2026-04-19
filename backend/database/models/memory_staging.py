"""
Memory Staging Model

Staging queue for memory items extracted by the consolidation pipeline.
Items land here for human review before committing to agent_memories.
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Column, Integer, String, DateTime, Text, Float,
    ForeignKey, Index,
)

from db import Base


class MemoryStaging(Base):
    __tablename__ = "memory_staging"
    __table_args__ = (
        Index("ix_staging_status", "status"),
        Index("ix_staging_tenant", "tenant_id"),
        Index("ix_staging_borrower", "borrower_id"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    borrower_id = Column(Integer, ForeignKey("leads.id"), nullable=False)
    source_call_id = Column(String(255), nullable=False)
    fact_text = Column(Text, nullable=False)
    fact_type = Column(String(50), nullable=False)
    topic = Column(String(100), nullable=True)
    confidence = Column(Float, nullable=False)
    transcript_span = Column(Text, nullable=True)
    fact_key = Column(String(255), nullable=True)
    destination = Column(String(50), nullable=False, default="memory")
    status = Column(String(20), nullable=False, default="pending_review")
    reviewed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    review_action = Column(String(20), nullable=True)
    committed_memory_id = Column(Integer, ForeignKey("agent_memories.id"), nullable=True)
    content_hash = Column(String(32), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
