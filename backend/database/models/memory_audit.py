"""
Memory Audit Event Model

Unified audit log for all memory operations: retrieval, extraction,
commit, supersession, rejection, exclusion, staging review, cache hit,
false-negative detection.
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Column, Integer, String, DateTime, Text,
    ForeignKey, Index,
)
from sqlalchemy.dialects.postgresql import JSONB

from db import Base


class MemoryAuditEvent(Base):
    __tablename__ = "memory_audit_events"
    __table_args__ = (
        Index("ix_audit_mem_org", "organization_id"),
        Index("ix_audit_mem_borrower", "borrower_id"),
        Index("ix_audit_mem_event", "event_type"),
        Index("ix_audit_mem_call", "source_call_id"),
        Index("ix_audit_mem_created", "created_at"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    borrower_id = Column(Integer, nullable=True)
    event_type = Column(String(50), nullable=False)
    source_call_id = Column(String(255), nullable=True)
    memory_id = Column(Integer, nullable=True)
    query_text = Column(Text, nullable=True)
    result_count = Column(Integer, nullable=True)
    latency_ms = Column(Integer, nullable=True)
    details = Column(JSONB, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
