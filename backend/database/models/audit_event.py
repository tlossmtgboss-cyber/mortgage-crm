"""
Server-Side Audit Event Model

Persistent audit log for SOC 2 Type II compliance. Append-only, queryable by
actor/resource/timeframe. Complements MobileAuditEvent (iOS-originated events)
with full server-side API event coverage.

Usage:
    from database.models.audit_event import AuditEvent
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID

from database import Base


class AuditEvent(Base):
    """
    One row per auditable event. Insert-only — never updated or deleted by app
    code. Retention is enforced by a periodic cleanup job (7 years for SOC 2
    financial controls, 13 months for general events).
    """

    __tablename__ = "audit_events"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
        default=lambda: uuid.uuid4(),
    )

    # When the event happened (server time, UTC)
    occurred_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )

    # What happened — use EventType constants from audit_service.py
    event_type = Column(String(64), nullable=False, index=True)

    # Outcome: success | failure | denied
    outcome = Column(
        String(16),
        nullable=False,
        server_default=text("'success'"),
        default="success",
    )

    # Who caused it
    actor_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    actor_email = Column(String(320), nullable=True)
    actor_role = Column(String(32), nullable=True)
    org_id = Column(UUID(as_uuid=True), nullable=True, index=True)

    # What it acted on
    resource_type = Column(String(64), nullable=True)
    resource_id = Column(String(128), nullable=True, index=True)

    # Request context
    ip = Column(INET, nullable=True)
    user_agent = Column(Text, nullable=True)
    request_id = Column(String(64), nullable=True)

    # Freeform structured details (before/after values, diff, etc.)
    # NO PII — use references, not copies.
    metadata_json = Column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )

    __table_args__ = (
        Index("ix_audit_actor_occurred", "actor_id", "occurred_at"),
        Index("ix_audit_resource", "resource_type", "resource_id", "occurred_at"),
        Index("ix_audit_metadata_gin", "metadata", postgresql_using="gin"),
    )
