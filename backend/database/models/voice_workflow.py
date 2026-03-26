"""Voice Workflow — persistent state machine for multi-step voice command workflows."""

from datetime import datetime, timedelta
from sqlalchemy import (
    Column, Integer, String, DateTime, Text, ForeignKey,
    Enum as SAEnum, Index, CheckConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from db import Base
import enum


class VoiceWorkflowState(str, enum.Enum):
    """States for voice-commanded async workflows."""
    INITIATED = "initiated"
    CONTACT_FOUND = "contact_found"
    SMS_SENT = "sms_sent"
    AWAITING_REPLY = "awaiting_reply"
    NEGOTIATING = "negotiating"
    TIME_CONFIRMED = "time_confirmed"
    APPOINTMENT_BOOKED = "appointment_booked"
    COMPLETED = "completed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    FAILED = "failed"


class VoiceWorkflowType(str, enum.Enum):
    """Types of voice-initiated workflows."""
    SCHEDULE_VIA_SMS = "schedule_via_sms"
    SEND_BOOKING_LINK = "send_booking_link"
    SEND_AND_SCHEDULE = "send_and_schedule"


class VoiceWorkflow(Base):
    __tablename__ = "voice_workflows"

    id = Column(Integer, primary_key=True, autoincrement=True)
    organization_id = Column(Integer, ForeignKey('organizations.id'), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)  # LO who initiated

    # Relationships
    organization = relationship("Organization", lazy="select")
    user = relationship("User", lazy="select")

    # Workflow type and state
    workflow_type = Column(String(50), nullable=False)
    state = Column(String(30), nullable=False, default=VoiceWorkflowState.INITIATED.value)

    # Contact info
    contact_name = Column(String(255))
    contact_phone = Column(String(20), index=True)  # For matching inbound SMS
    contact_email = Column(String(255))
    lead_id = Column(Integer, ForeignKey('leads.id'), nullable=True)

    # Relationship for lead (nullable)
    lead = relationship("Lead", lazy="select")

    # Scheduling context
    meeting_type = Column(String(50), default="discovery_call")
    meeting_duration_minutes = Column(Integer, default=30)
    message_context = Column(Text, nullable=True)  # "discuss rate options"

    # Conversation tracking
    # conversation_history schema: [{"role": "system"|"user"|"assistant"|"contact", "content": str, "timestamp": str (ISO 8601)}]
    conversation_history = Column(JSONB, nullable=False, server_default='[]')
    turn_count = Column(Integer, default=0)
    max_turns = Column(Integer, default=8)

    # Confirmed scheduling details
    confirmed_datetime = Column(DateTime, nullable=True)
    # appointment_id references smart_scheduler appointments; no FK because the appointments
    # table uses a UUID primary key and may not exist in all deployments.
    appointment_id = Column(Integer, nullable=True)

    # Slot proposals sent to contact
    proposed_slots = Column(JSONB, default=list)  # [{start, end, formatted}]

    # Lifecycle
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)  # Auto-expire after 48h
    completed_at = Column(DateTime, nullable=True)

    # Error tracking
    error_message = Column(Text, nullable=True)
    last_sms_sent_at = Column(DateTime, nullable=True)
    last_sms_received_at = Column(DateTime, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "state IN ('initiated', 'contact_found', 'sms_sent', 'awaiting_reply', 'negotiating', "
            "'time_confirmed', 'appointment_booked', 'completed', 'expired', 'cancelled', 'failed')",
            name='ck_voice_workflows_state',
        ),
        Index("ix_voice_workflows_phone_state", "contact_phone", "state"),
        Index("ix_voice_workflows_org_user", "organization_id", "user_id"),
        Index("ix_voice_workflows_expires", "expires_at"),
        {'extend_existing': True},
    )

    def is_active(self):
        """Check if workflow is in an active (non-terminal) state."""
        terminal = {
            VoiceWorkflowState.COMPLETED.value,
            VoiceWorkflowState.EXPIRED.value,
            VoiceWorkflowState.CANCELLED.value,
            VoiceWorkflowState.FAILED.value,
        }
        return self.state not in terminal

    def add_message(self, role: str, content: str):
        """Append a message to conversation history.

        NOTE: For concurrent-safe appends, use add_message_atomic() with a DB session
        instead of this method. This method is still useful for in-memory workflow
        construction before the first flush.
        """
        if self.conversation_history is None:
            self.conversation_history = []
        self.conversation_history = self.conversation_history + [{
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow().isoformat(),
        }]
        if role == "contact":
            self.turn_count = (self.turn_count or 0) + 1

    @classmethod
    def add_message_atomic(cls, db_session, workflow_id: int, role: str, content: str):
        """Atomically append a message to conversation_history using PostgreSQL JSONB concat.

        This avoids the read-modify-write race condition by using a single UPDATE
        statement with JSONB || operator. Use this for all message appends after
        the workflow is persisted.
        """
        from sqlalchemy import text
        new_entry = {
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow().isoformat(),
        }
        import json
        db_session.execute(
            text("""
                UPDATE voice_workflows
                SET conversation_history = COALESCE(conversation_history, '[]'::jsonb) || :new_entry::jsonb,
                    turn_count = CASE WHEN :role = 'contact' THEN COALESCE(turn_count, 0) + 1 ELSE turn_count END,
                    updated_at = NOW()
                WHERE id = :workflow_id
            """),
            {
                "new_entry": json.dumps([new_entry]),
                "role": role,
                "workflow_id": workflow_id,
            },
        )
        db_session.flush()

    def transition_to(self, new_state: str):
        """Transition to a new state with timestamp."""
        self.state = new_state
        self.updated_at = datetime.utcnow()
        if new_state in (VoiceWorkflowState.COMPLETED.value, VoiceWorkflowState.APPOINTMENT_BOOKED.value):
            self.completed_at = datetime.utcnow()
