"""
05-audit-logs/model.py

Persistent audit log for SOC 2 Type II. Append-only, queryable by
actor/resource/timeframe. Does NOT replace application logs (those are
ephemeral by design); this is the durable compliance trail.

Drop-in: backend/app/models/audit_event.py
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

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
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class AuditEvent(Base):
    """
    One row per auditable event. Insert-only — never updated or deleted by app
    code. Retention is enforced by a periodic cleanup job (7 years for SOC 2
    financial controls, 13 months for general events — configurable).
    """

    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    # When the event happened (server time, UTC)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
        index=True,
    )

    # What happened — use enum-style constants in code (see event_types.py)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # Outcome of the event
    outcome: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=text("'success'"),
    )  # success | failure | denied

    # Who caused it
    actor_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    actor_email: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)
    actor_role: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    org_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )

    # What it acted on
    resource_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    resource_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)

    # Request context
    ip: Mapped[Optional[str]] = mapped_column(INET, nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    request_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Freeform structured details (before/after values, diff, etc.)
    # NO PII — use references, not copies. SSN-before / SSN-after = "SET" / "SET", never values.
    metadata_json: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )

    __table_args__ = (
        # Composite index for "what did user X do in the last N days"
        Index("ix_audit_actor_occurred", "actor_id", "occurred_at"),
        # Composite for "what happened to resource R"
        Index("ix_audit_resource", "resource_type", "resource_id", "occurred_at"),
        # JSONB GIN for metadata searches
        Index("ix_audit_metadata_gin", "metadata", postgresql_using="gin"),
    )
