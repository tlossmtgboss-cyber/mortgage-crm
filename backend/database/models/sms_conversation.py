"""SMS conversation threading models."""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Integer, Float, Text, JSON, ForeignKey, Index, Boolean
from db import Base


def _uuid():
    return str(uuid.uuid4())


class SMSConversation(Base):
    __tablename__ = "sms_conversations"
    __table_args__ = (
        Index("ix_sms_conv_phone_org", "phone_number", "organization_id"),
        {"extend_existing": True},
    )

    id = Column(String, primary_key=True, default=_uuid)
    phone_number = Column(String, nullable=False)
    lead_id = Column(String, ForeignKey("leads.id"), nullable=True)
    organization_id = Column(String, nullable=False)
    status = Column(String, default="active")  # active, paused, closed, converted
    current_stage = Column(String, default="greeting")  # greeting, qualifying, scheduling, nurture, objection_handling
    context_data = Column(JSON, default=dict)  # accumulated qualification data
    close_reason = Column(String, nullable=True)
    last_message_at = Column(DateTime, nullable=True)
    message_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class SMSConversationMessage(Base):
    __tablename__ = "sms_conversation_messages"

    id = Column(String, primary_key=True, default=_uuid)
    conversation_id = Column(String, ForeignKey("sms_conversations.id"), nullable=False, index=True)
    direction = Column(String, nullable=False)  # inbound, outbound
    content = Column(Text, nullable=False)
    intent = Column(String, nullable=True)
    confidence = Column(Float, nullable=True)
    intent_method = Column(String, nullable=True)  # keyword, llm
    entities = Column(JSON, default=dict)
    ai_generated = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
