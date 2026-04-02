"""
AI Prospect Re-Engagement Conversation Models

Tracks multi-turn AI SMS conversations for re-engaging stale leads.
State machine manages the lifecycle from initial outreach to appointment booking.
"""

import enum
import logging
from datetime import datetime, timedelta

from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Text, Index,
    ForeignKey, Enum as SAEnum, JSON,
)
from sqlalchemy.orm import relationship

from db import Base

logger = logging.getLogger(__name__)


class ConversationState(str, enum.Enum):
    """State machine for AI prospect re-engagement conversations."""
    PENDING_OUTREACH = "pending_outreach"
    INITIAL_OUTREACH_SENT = "initial_outreach_sent"
    AWAITING_REPLY = "awaiting_reply"
    SCHEDULING = "scheduling"
    APPOINTMENT_BOOKED = "appointment_booked"
    DECLINED = "declined"
    OPT_OUT = "opt_out"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


# Terminal states — no further messages should be sent
TERMINAL_STATES = {
    ConversationState.APPOINTMENT_BOOKED,
    ConversationState.DECLINED,
    ConversationState.OPT_OUT,
    ConversationState.EXPIRED,
    ConversationState.CANCELLED,
}

# Active states — webhook should intercept replies
ACTIVE_STATES = {
    ConversationState.INITIAL_OUTREACH_SENT,
    ConversationState.AWAITING_REPLY,
    ConversationState.SCHEDULING,
}


class AIProspectConversation(Base):
    __tablename__ = "ai_prospect_conversations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=False)
    lo_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Phone numbers for SMS routing
    lead_phone = Column(String(20), nullable=False, index=True)
    telnyx_from_number = Column(String(20), nullable=False)

    # State machine
    state = Column(String(30), nullable=False, default=ConversationState.PENDING_OUTREACH.value)
    state_changed_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Conversation data (JSONB)
    context = Column(JSON, default=dict)       # lo_name, lead info, cached slots
    messages = Column(JSON, default=list)       # [{role, content, timestamp}]
    proposed_times = Column(JSON, default=list) # suggested appointment times

    # Outcome tracking
    booked_appointment_id = Column(String(50), nullable=True)
    outcome = Column(String(50), nullable=True)
    outcome_notes = Column(Text, nullable=True)
    task_id = Column(Integer, nullable=True)

    # Turn management
    turn_count = Column(Integer, default=0)
    max_turns = Column(Integer, default=8)

    # Timing
    expires_at = Column(DateTime, nullable=True)
    first_outreach_at = Column(DateTime, nullable=True)
    last_message_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        # Partial unique index: only one active conversation per phone number
        Index(
            "ix_ai_prospect_conv_active_phone",
            "lead_phone",
            unique=True,
            postgresql_where=(
                Column("state").in_([s.value for s in ACTIVE_STATES])
            ),
        ),
        # Index for expiry scan
        Index("ix_ai_prospect_conv_expires", "expires_at", "state"),
        # Index for org + state queries
        Index("ix_ai_prospect_conv_org_state", "organization_id", "state"),
    )

    def __repr__(self):
        return f"<AIProspectConversation id={self.id} lead={self.lead_id} state={self.state}>"


class AIReengagementConfig(Base):
    __tablename__ = "ai_reengagement_config"

    id = Column(Integer, primary_key=True, autoincrement=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), unique=True, nullable=False)
    enabled = Column(Boolean, default=False)
    stale_days = Column(Integer, default=30)
    daily_limit = Column(Integer, default=20)
    max_turns = Column(Integer, default=8)
    expiry_days = Column(Integer, default=7)
    initial_message_template = Column(Text, nullable=True)
    eligible_stages = Column(JSON, default=list)  # ["Prospect", "Long-Term Nurture", ...]
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<AIReengagementConfig org={self.organization_id} enabled={self.enabled}>"


def create_tables_if_needed(engine):
    """Create ai_prospect_conversations and ai_reengagement_config tables if they don't exist."""
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    existing = inspector.get_table_names()

    if "ai_prospect_conversations" not in existing:
        AIProspectConversation.__table__.create(engine, checkfirst=True)
        logger.info("Created table: ai_prospect_conversations")

        # Create partial unique index manually (SQLAlchemy partial index support varies)
        try:
            with engine.connect() as conn:
                conn.execute(text("""
                    CREATE UNIQUE INDEX IF NOT EXISTS ix_ai_prospect_conv_active_phone
                    ON ai_prospect_conversations (lead_phone)
                    WHERE state IN ('initial_outreach_sent', 'awaiting_reply', 'scheduling')
                """))
                conn.commit()
                logger.info("Created partial unique index on lead_phone for active states")
        except Exception as e:
            logger.warning(f"Partial index creation skipped (may already exist): {e}")

    if "ai_reengagement_config" not in existing:
        AIReengagementConfig.__table__.create(engine, checkfirst=True)
        logger.info("Created table: ai_reengagement_config")
