"""
Briefing Thread Models

Tracks the full lifecycle of an interactive morning briefing session:
- BriefingThread: The conversation state machine (BRIEFING_SENT → AWAITING_REPLY →
  AWAITING_APPROVAL → EXECUTING → COMPLETE/ABANDONED)
- BriefingTask: Individual action items extracted from LO replies, queued for execution
- BriefingAuditLog: Append-only tamper-evident audit chain for compliance

Models:
    - BriefingThread: Per-user briefing reply thread with state machine
    - BriefingTask: Extracted tasks pending LO approval / execution
    - BriefingAuditLog: Immutable hash-chained audit trail

Usage:
    from database.models.briefing_thread import BriefingThread, BriefingTask, BriefingAuditLog

    thread = BriefingThread(
        organization_id=org_id,
        user_id=user_id,
        morning_briefing_id=briefing_id,
        briefing_items=[...],
    )
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import text

from db import Base


def _utcnow():
    """Return current UTC time as a timezone-aware datetime."""
    return datetime.now(timezone.utc)


# =============================================================================
# BRIEFING THREAD — per-user reply conversation state machine
# =============================================================================

class BriefingThread(Base):
    """State machine tracking a single morning-briefing reply conversation.

    Lifecycle states:
        BRIEFING_SENT → AWAITING_REPLY → AWAITING_APPROVAL → EXECUTING →
        COMPLETE | ABANDONED | EXPIRED
    """
    __tablename__ = "briefing_threads"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(
        Integer, ForeignKey("organizations.id"), nullable=False, index=True
    )
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    morning_briefing_id = Column(
        Integer, ForeignKey("morning_briefings.id"), nullable=True
    )

    # Token used to correlate inbound SMS/email reply to this thread
    thread_token = Column(
        UUID(as_uuid=True),
        default=uuid.uuid4,
        unique=True,
        nullable=False,
        index=True,
    )

    # Provider-assigned message ID of the outbound briefing message
    outbound_message_id = Column(String(512), nullable=True)

    # State machine
    state = Column(String(50), nullable=False, default="BRIEFING_SENT")

    # Trust level for autonomous execution (1=full-auto … 5=require-explicit-approval)
    trust_mode = Column(Integer, nullable=False, default=3)

    # How many follow-up loops have occurred in this thread
    loop_count = Column(Integer, nullable=False, default=0)

    # Structured briefing content sent to the LO
    briefing_items = Column(JSONB, nullable=True)

    # Tasks extracted from AI analysis of LO reply
    extracted_tasks = Column(JSONB, nullable=True)

    # Raw inbound reply text from the loan officer
    lo_reply_raw = Column(Text, nullable=True)

    # Raw approval/confirmation text from the LO (AWAITING_APPROVAL → EXECUTING)
    lo_approval_raw = Column(Text, nullable=True)

    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    # Relationships
    tasks = relationship(
        "BriefingTask",
        back_populates="thread",
        cascade="all, delete-orphan",
    )
    audit_entries = relationship(
        "BriefingAuditLog",
        back_populates="thread",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        # Composite lookup: org + user + state (e.g. find all active threads for user)
        Index("ix_briefing_threads_org_user_state", "organization_id", "user_id", "state"),
        # Partial index: active threads nearing expiry (scheduler sweep)
        Index(
            "ix_briefing_threads_active_expiry",
            "organization_id", "expires_at",
            postgresql_where=text("state IN ('AWAITING_REPLY', 'AWAITING_APPROVAL')"),
        ),
        # Fast lookup by provider message ID (inbound SMS webhook)
        Index("ix_briefing_threads_outbound_message_id", "outbound_message_id"),
        # thread_token uniqueness is enforced by unique=True on the column;
        # explicit named constraint for migrations
        UniqueConstraint("thread_token", name="uq_briefing_threads_token"),
    )


# =============================================================================
# BRIEFING TASK — individual action item extracted from LO reply
# =============================================================================

class BriefingTask(Base):
    """An action item extracted from a briefing reply, queued for execution.

    Each task maps to a single @mortgage_tool invocation. Status transitions:
        pending → preflight_check → approved → executing → done | failed | skipped
    """
    __tablename__ = "briefing_tasks"

    id = Column(Integer, primary_key=True, index=True)
    thread_id = Column(
        Integer, ForeignKey("briefing_threads.id"), nullable=False
    )
    organization_id = Column(Integer, nullable=False, index=True)

    # Which numbered briefing item this task originated from (1-based)
    briefing_item_number = Column(Integer, nullable=True)
    briefing_item_summary = Column(Text, nullable=True)

    # Execution intent
    action_type = Column(String(50), nullable=True)
    action_params = Column(JSONB, nullable=True)
    tool_name = Column(String(100), nullable=True)

    # LO free-text override or clarification
    lo_override_notes = Column(Text, nullable=True)

    # AI extraction confidence [0.0, 1.0]
    confidence_score = Column(Float, nullable=True)

    # Risk classification: low | medium | high | critical
    risk_level = Column(String(20), nullable=False, default="low")

    # Result of dry-run / pre-flight validation
    preflight_result = Column(JSONB, nullable=True)

    # Unique key for at-most-once execution semantics
    idempotency_key = Column(String(255), unique=True, nullable=True)

    # Current status of the task
    status = Column(String(30), nullable=False, default="pending")

    # Optional future date this task should carry over to if not executed today
    carryover_target_date = Column(Date, nullable=True)

    # Tool result payload on success
    result_data = Column(JSONB, nullable=True)

    # Human-readable error message on failure
    error_message = Column(Text, nullable=True)

    # Timestamp when the tool was actually invoked
    executed_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    # Relationships
    thread = relationship("BriefingThread", back_populates="tasks")

    __table_args__ = (
        Index("ix_briefing_tasks_thread_status", "thread_id", "status"),
        Index("ix_briefing_tasks_organization_id", "organization_id"),
    )


# =============================================================================
# BRIEFING AUDIT LOG — append-only hash-chained compliance log
# =============================================================================

class BriefingAuditLog(Base):
    """Immutable, hash-chained audit trail for all briefing thread events.

    Design constraints:
        - APPEND-ONLY: no UPDATE or DELETE operations
        - payload_hash: SHA-256 of the payload (integrity check)
        - prev_hash: hash of the previous entry's payload_hash (chain integrity)
        - BigInteger PK for high-throughput multi-tenant environments
    """
    __tablename__ = "briefing_audit_logs"

    id = Column(BigInteger, primary_key=True, index=True)
    organization_id = Column(Integer, nullable=False, index=True)
    thread_id = Column(
        Integer, ForeignKey("briefing_threads.id"), nullable=True
    )
    task_id = Column(
        Integer, ForeignKey("briefing_tasks.id"), nullable=True
    )

    # Categorised event name (e.g. "thread_created", "reply_received", "task_executed")
    event_type = Column(String(50), nullable=True)

    # Who triggered the event: "system", "aria", "user:<user_id>", etc.
    actor = Column(String(100), nullable=True)

    # Arbitrary structured event payload
    payload = Column(JSONB, nullable=True)

    # SHA-256 hex digest of the serialised payload (tamper detection)
    payload_hash = Column(String(64), nullable=True)

    # Hash of the previous log entry in this thread (chain integrity)
    prev_hash = Column(String(64), nullable=True)

    created_at = Column(DateTime(timezone=True), default=_utcnow, index=True)

    # Relationships
    thread = relationship("BriefingThread", back_populates="audit_entries")

    __table_args__ = (
        Index("ix_briefing_audit_logs_org_created_at", "organization_id", "created_at"),
    )
